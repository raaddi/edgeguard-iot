"""Application outcomes, replay protection and real MQTT command round trips."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from contracts.commands import command_topic, decode_result, result_topic
from edge.mqtt import Connection
from simulator.control import CommandProcessor, CommandReceiver
from simulator.house import HouseSimulation
from simulator.telemetry import session_id


def request(sim, component="led_01", value=1, node=None, **changes):
    node = node or sim.components[component]["node"]
    return {"schema_version": "1.0", "command_id": str(uuid4()), "device_id": node,
            "target_boot_id": session_id(sim.run_id, node), "component_id": component,
            "operation": "set", "value": value, "observed_uptime_ms": 0,
            "expires_uptime_ms": 5000, **changes}


def test_duplicate_returns_original_even_after_expiry_without_second_action():
    sim = HouseSimulation(node_count=1)
    processor = CommandProcessor(sim)
    command = request(sim)
    original = processor.handle(command)
    assert original["status"] == "accepted"
    for _ in range(6):
        sim.step()
    assert processor.handle(deepcopy(command)) == original
    assert len(sim.actions) == 1
    changed = {**command, "value": 0, "expires_uptime_ms": 10000}
    assert processor.handle(changed)["reason"] == "duplicate_conflict"
    assert sim.actuators["led_01"]["commanded"] == 1
    assert processor.handle(command) == original
    # Caller mutation cannot poison the cache.
    original["status"] = "rejected"
    assert processor.handle(command)["status"] == "accepted"


@pytest.mark.parametrize("changes,reason", [
    ({"target_boot_id": str(uuid4())}, "wrong_boot"),
    ({"expires_uptime_ms": 1}, "expired"),
    ({"observed_uptime_ms": 2000, "expires_uptime_ms": 3000}, "not_yet_valid"),
    ({"component_id": "missing"}, "unknown_component"),
    ({"component_id": "gas_01"}, "unsupported_operation"),
    ({"operation": "auto", "value": None}, "unsupported_operation"),
    ({"value": 110}, "value_out_of_range"),
])
def test_rejections_never_mutate_model(changes, reason):
    sim = HouseSimulation(node_count=1)
    sim.step()
    before = sim.export()
    result = CommandProcessor(sim).handle(request(sim, **changes))
    assert result["status"] == "rejected" and result["reason"] == reason
    assert sim.export() == before


def test_capability_ownership_auto_offline_and_action_failure(monkeypatch):
    sim = HouseSimulation(node_count=3, extra_nodes=2)
    processor = CommandProcessor(sim)
    node = sim.components["fan_01"]["node"]
    assert processor.handle(request(sim, "fan_01"))["status"] == "accepted"
    assert sim.actuators["fan_01"]["mode"] == "manual"
    assert processor.handle(request(sim, "fan_01", operation="auto", value=None))["status"] == "accepted"
    assert sim.actuators["fan_01"]["mode"] == "auto"
    other = next(n for n in sim.nodes if n != node)
    assert processor.handle(request(sim, "fan_01", node=other))["reason"] == "unknown_component"
    assert processor.handle(request(sim, "virtual_gas_01"))["reason"] == "unsupported_operation"
    sim.inject("node_offline", node, 1)
    sim.step()
    count = len(sim.actions)
    assert processor.handle(request(sim, "fan_01")) is None
    assert len(sim.actions) == count
    sim.step()
    monkeypatch.setattr(sim, "MAX_ACTIONS", len(sim.actions))
    assert processor.handle(request(sim, "fan_01"))["reason"] == "capacity_exceeded"
    monkeypatch.setattr(sim, "MAX_ACTIONS", 1000)
    def fail(*args):
        raise ValueError("Driver rejected operation")
    monkeypatch.setattr(sim, "command", fail)
    assert processor.handle(request(sim, "fan_01"))["reason"] == "internal_error"


def test_cache_capacity_does_not_evict_or_reexecute(monkeypatch):
    sim = HouseSimulation(node_count=1)
    processor = CommandProcessor(sim)
    monkeypatch.setattr(processor, "CACHE_PER_NODE", 1)
    first = request(sim)
    accepted = processor.handle(first)
    assert processor.handle(request(sim, value=0))["reason"] == "capacity_exceeded"
    for _ in range(6):
        sim.step()
    assert processor.handle(first) == accepted
    assert len(sim.actions) == 1
    assert processor.handle({**first, "target_boot_id": str(uuid4())})["reason"] == "wrong_boot"
    assert processor.handle(first) == accepted


def test_receiver_bounds_and_validation_before_queueing():
    sim = HouseSimulation(node_count=1)
    receiver = CommandReceiver(sim, SimpleNamespace(client=SimpleNamespace()))
    packet = SimpleNamespace(topic=command_topic("esp32_node_01"), retain=False,
                             payload=json.dumps(request(sim)).encode())
    for _ in range(receiver.QUEUE_LIMIT + 2):
        receiver._message(None, None, packet)
    assert len(receiver.pending) == receiver.QUEUE_LIMIT
    assert receiver.counts["queue_full"] == 2
    packet.payload = b"{" * 5000
    receiver._message(None, None, packet)
    assert receiver.counts["invalid"] == 1
    packet.retain = True
    receiver._message(None, None, packet)
    assert receiver.counts["retained"] == 1
    assert not sim.actions


def pump_until(receiver, sender, predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        receiver.service()
        sender.pump()
        assert time.monotonic() < deadline


def test_real_broker_command_result_and_following_telemetry(broker):
    sim = HouseSimulation(node_count=3, extra_nodes=2)
    node_connection, sender = Connection(broker.port), Connection(broker.port)
    receiver = CommandReceiver(sim, node_connection)
    replies, reports = [], []
    command = request(sim, "servo_01", 110)
    node = command["device_id"]
    def received(client, userdata, packet):
        if packet.topic == result_topic(node):
            replies.append(decode_result(packet.payload, topic=packet.topic))
        else:
            reports.append(json.loads(packet.payload))
    sender.client.on_message = received
    try:
        receiver.connect()
        sender.connect()
        sender.subscribe([result_topic(node), f"edgeguard/devices/{node}/telemetry"])
        receiver.publish_telemetry()
        sender.publish(command_topic(node), json.dumps(command).encode())
        pump_until(receiver, sender, lambda: len(replies) == 1 and len(reports) == 1)
        assert replies[0]["status"] == "accepted"
        assert reports[0]["actuators"]["servo_01"]["commanded"] == 0
        sim.step()
        receiver.publish_telemetry()
        sender.publish(command_topic(node), json.dumps(command).encode())
        pump_until(receiver, sender, lambda: len(replies) == 2 and len(reports) == 2)
        assert replies[0] == replies[1] and len(sim.actions) == 1
        assert reports[1]["actuators"]["servo_01"]["commanded"] == 110
        assert reports[1]["actuators"]["servo_01"]["feedback"] == "simulated"
        sender.publish(command_topic(node), json.dumps({**command, "value": 0}).encode())
        pump_until(receiver, sender, lambda: len(replies) == 3)
        assert replies[-1]["reason"] == "duplicate_conflict"
        sim.step()
        expired = request(sim, "servo_01", 0, expires_uptime_ms=1000)
        sender.publish(command_topic(node), json.dumps(expired).encode())
        pump_until(receiver, sender, lambda: len(replies) == 4)
        assert replies[-1]["reason"] == "expired" and len(sim.actions) == 1
        assert HouseSimulation.replay(sim.export()).export() == sim.export()
    finally:
        sender.close()
        node_connection.close()


def test_retained_command_on_subscription_is_not_executed(broker):
    sim = HouseSimulation(node_count=1)
    sender, connection = Connection(broker.port), Connection(broker.port)
    receiver = CommandReceiver(sim, connection)
    try:
        sender.connect()
        info = sender.client.publish(command_topic("esp32_node_01"), json.dumps(request(sim)), qos=1, retain=True)
        deadline = time.monotonic() + 5
        while not info.is_published():
            sender.pump()
            assert time.monotonic() < deadline
        receiver.connect()
        pump_until(receiver, sender, lambda: receiver.counts["retained"] == 1)
        assert not sim.actions and not receiver.pending
    finally:
        connection.close()
        sender.close()


def test_cli_sender_uses_fresh_observation_and_node_result(broker):
    sim = HouseSimulation(node_count=1)
    connection = Connection(broker.port)
    receiver = CommandReceiver(sim, connection)
    process = None
    try:
        receiver.connect()
        process = subprocess.Popen([sys.executable, "-m", "edge.command", "--port", str(broker.port),
                                    "--device", "esp32_node_01", "--component", "led_01", "--value", "1"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 12
        while process.poll() is None:
            receiver.service()
            sim.step()
            receiver.publish_telemetry()
            assert time.monotonic() < deadline
        stdout, stderr = process.communicate(timeout=3)
        assert process.returncode == 0, (stdout, stderr)
        sent, result = [json.loads(line) for line in stdout.splitlines()]
        assert sent["command"]["observed_uptime_ms"] > 0
        assert result["result"]["status"] == "accepted"
        assert len(sim.actions) == 1 and sim.actuators["led_01"]["commanded"] == 1
    finally:
        if process and process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)
        connection.close()


def test_failed_result_publish_keeps_outcome_and_no_second_action(monkeypatch):
    sim = HouseSimulation(node_count=1)
    def fail(*args):
        raise ConnectionError("Disconnected before PUBACK")
    connection = SimpleNamespace(client=SimpleNamespace(), pump=lambda: None, publish=fail)
    receiver = CommandReceiver(sim, connection)
    command = request(sim)
    receiver.pending.append(command)
    with pytest.raises(ConnectionError):
        receiver.service()
    assert len(sim.actions) == 1
    assert receiver.processor.handle(command)["status"] == "accepted"
    assert len(sim.actions) == 1
    assert receiver.counts["results_broker_acked"] == 0
    assert receiver.events[-1]["result"]["status"] == "accepted"


def test_accepted_setpoint_does_not_claim_actuator_feedback():
    sim = HouseSimulation(node_count=1)
    sim.inject("fan_failure", "fan_01", 5)
    sim.step()
    result = CommandProcessor(sim).handle(request(sim, "fan_01"))
    assert result["status"] == "accepted"
    sim.step()
    state = sim.history[-1]["actuators"]["fan_01"]
    assert state["commanded"] == 1 and state["reported"] == 0
    assert state["feedback"] == "simulated"


def test_queued_command_is_checked_at_handling_time():
    sim = HouseSimulation(node_count=1)
    published = []
    connection = SimpleNamespace(client=SimpleNamespace(), pump=lambda: None,
                                 publish=lambda topic, payload: published.append(json.loads(payload)))
    receiver = CommandReceiver(sim, connection)
    receiver.pending.append(request(sim, expires_uptime_ms=1000))
    sim.step()
    receiver.service()
    assert published[0]["reason"] == "expired"
    assert not sim.actions


def test_sender_without_fresh_telemetry_does_not_publish(broker, capsys):
    from edge.command import send_command
    connection = Connection(broker.port)
    try:
        connection.connect()
        with pytest.raises(TimeoutError, match="no command sent"):
            send_command(connection, "esp32_node_01", "led_01", value=1, timeout=0.2)
        assert connection.acknowledged == 0
        assert not capsys.readouterr().out
    finally:
        connection.close()


def test_receiver_stops_on_broker_loss(broker):
    connection = Connection(broker.port)
    receiver = CommandReceiver(HouseSimulation(node_count=1), connection)
    try:
        receiver.connect()
        broker.stop()
        with pytest.raises(ConnectionError):
            receiver.run(steps=2, interval=0.05)
    finally:
        connection.close()


def test_failed_command_runner_exports_diagnostics(tmp_path, monkeypatch):
    import simulator.mqtt as runner
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["mqtt", "--commands", "--run-id", "failed-control", "--steps", "2"])
    def fail(self):
        raise ConnectionError("Broker unavailable")
    monkeypatch.setattr(Connection, "connect", fail)
    assert runner.main() == 1
    path = Path("experiments/runs/failed-control-mqtt.json")
    archive = json.loads(path.read_text())
    assert archive["transport"]["status"] == "failed"
    assert archive["control"]["pending_at_stop"] == 0
    with pytest.raises(SystemExit):
        runner.main()
