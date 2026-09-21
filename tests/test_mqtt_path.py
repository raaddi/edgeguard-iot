"""Exercise the real Mosquitto transport, not a mock MQTT server."""

from copy import deepcopy
import json
import sqlite3
from types import SimpleNamespace
import threading
import time

import pytest

from contracts.telemetry import MAX_PAYLOAD_BYTES, TelemetryError, telemetry_topic
from edge.collector import Collector
from edge.mqtt import Connection
from edge.storage import TelemetryStore
from simulator.house import HouseSimulation
from simulator.mqtt import publish_run


def wait_until(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.03)
    raise AssertionError("Timed out waiting for MQTT condition")


class RunningCollector:
    def __init__(self, tmp_path, port):
        self.database = tmp_path / "telemetry.sqlite3"
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.errors = []
        self.collector = None

        def run():
            collector = None
            try:
                collector = self.collector = Collector(self.database, port)
                collector.run(on_ready=self.ready.set, stop=self.stop)
            except Exception as error:
                self.errors.append(error)
                self.ready.set()
            finally:
                if collector:
                    collector.close()
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        assert self.ready.wait(8)
        assert not self.errors

    def count(self):
        with sqlite3.connect(self.database) as db:
            return db.execute("SELECT count(*) FROM telemetry").fetchone()[0]

    def close(self):
        self.stop.set()
        self.thread.join(8)
        assert not self.thread.is_alive()
        assert not self.errors


@pytest.fixture
def receiver(broker, tmp_path):
    running = RunningCollector(tmp_path, broker.port)
    try:
        yield running
    finally:
        running.close()


@pytest.fixture
def sender(broker):
    connection = Connection(broker.port)
    connection.connect()
    try:
        yield connection
    finally:
        connection.close()


def test_store_validation_duplicate_conflict_and_restart(tmp_path):
    path = tmp_path / "telemetry.sqlite3"
    message = HouseSimulation(node_count=1).history[0]
    topic = telemetry_topic(message["device_id"])
    store = TelemetryStore(path)
    assert store.ingest(topic, json.dumps(message).encode(), received_at="2026-09-19T12:00:00Z") == "stored"
    assert store.ingest(topic, json.dumps(message, indent=4).encode()) == "duplicate"
    changed = deepcopy(message)
    changed["uptime_ms"] += 1
    assert store.ingest(topic, json.dumps(changed).encode()) == "conflict"
    for payload in [b'{"bad":true}', b'{}' * MAX_PAYLOAD_BYTES]:
        with pytest.raises(TelemetryError):
            store.ingest(topic, payload)
    with pytest.raises(TelemetryError):
        store.ingest(telemetry_topic("wrong_node"), json.dumps(message).encode())
    store.close()
    reopened = TelemetryStore(path)
    assert reopened.ingest(topic, json.dumps(message).encode()) == "duplicate"
    row = reopened.db.execute("SELECT received_at, device_timestamp, payload FROM telemetry").fetchone()
    assert row[0] == "2026-09-19T12:00:00Z" and row[1] == message["timestamp"]
    assert json.loads(row[2]) == message
    rebooted = HouseSimulation(node_count=1, run_id="another-boot").history[0]
    assert reopened.ingest(topic, json.dumps(rebooted).encode()) == "stored"
    reopened.close()


def test_house_through_mqtt_to_sqlite_with_offline_gap(receiver, sender):
    from fastapi.testclient import TestClient
    from edge.api import create_app

    sim = HouseSimulation(node_count=3, extra_nodes=2, run_id="mqtt-integration")
    sim.inject("node_offline", "esp32_node_01", 2)
    assert publish_run(sim, sender, steps=5, interval=0) == 23
    wait_until(lambda: receiver.count() == 23)
    with sqlite3.connect(receiver.database) as db:
        messages = [json.loads(row[0]) for row in db.execute("SELECT payload FROM telemetry")]
        assert {m["device_id"] for m in messages} == set(sim.nodes)
        assert {m["sequence_number"] for m in messages if m["device_id"] == "esp32_node_01"} == {0, 3, 4}
        assert sorted(messages, key=lambda m: (m["device_id"], m["sequence_number"])) == sorted(
            sim.history, key=lambda m: (m["device_id"], m["sequence_number"]))
    # Read committed WAL data while the real MQTT collector is still running.
    with TestClient(create_app(receiver.database)) as api:
        assert api.get('/health').status_code == 200
        assert sum(item['message_count'] for item in api.get('/devices').json()['items']) == 23
        records = api.get('/devices/esp32_node_01/telemetry').json()['items']
        assert [r['telemetry']['sequence_number'] for r in records] == [0, 3, 4]
        assert all(r['telemetry'] in messages for r in records)


def test_invalid_duplicate_and_conflict_do_not_stop_collector(receiver, sender):
    sim = HouseSimulation(node_count=1)
    message = sim.history[0]
    topic = telemetry_topic(message["device_id"])
    sender.publish(topic, json.dumps(message).encode())
    sender.publish(topic, json.dumps(message).encode())
    changed = deepcopy(message)
    changed["uptime_ms"] += 5
    sender.publish(topic, json.dumps(changed).encode())
    sender.publish(topic, b'not-json')
    sender.publish(telemetry_topic("wrong"), json.dumps(message).encode())
    sim.step()
    sender.publish(topic, json.dumps(sim.history[-1]).encode())
    wait_until(lambda: receiver.collector.counts["stored"] == 2)
    assert receiver.collector.counts["duplicate"] == 1
    assert receiver.collector.counts["conflict"] == 1
    assert receiver.collector.counts["invalid"] == 2
    assert receiver.count() == 2


def test_collector_resubscribes_after_broker_restart(receiver, sender, broker):
    sim = HouseSimulation(node_count=1)
    publish_run(sim, sender, steps=1, interval=0)
    wait_until(lambda: receiver.count() == 1)
    broker.stop()
    wait_until(lambda: receiver.collector.counts["disconnects"] > 0)
    broker.start()
    wait_until(lambda: receiver.collector.counts["connections"] >= 2 and receiver.collector.ready)
    replacement = Connection(broker.port)
    try:
        replacement.connect()
        publish_run(sim, replacement, steps=2, interval=0)
        wait_until(lambda: receiver.count() == 2)
        assert receiver.collector.counts["duplicate"] == 1
    finally:
        replacement.close()


def test_retained_snapshot_is_not_a_fresh_measurement(broker, sender, tmp_path):
    message = HouseSimulation(node_count=1).history[0]
    info = sender.client.publish(telemetry_topic(message["device_id"]), json.dumps(message), qos=1, retain=True)
    deadline = time.monotonic() + 3
    while not info.is_published():
        sender.pump()
        assert time.monotonic() < deadline
    receiver = RunningCollector(tmp_path, broker.port)
    try:
        wait_until(lambda: receiver.collector.counts["retained"] == 1)
        assert receiver.count() == 0
    finally:
        receiver.close()


def test_failed_sqlite_commit_is_not_acknowledged(tmp_path):
    collector = Collector(tmp_path / "failed.sqlite3")
    collector.store.db.execute("""CREATE TRIGGER reject_insert BEFORE INSERT ON telemetry
        BEGIN SELECT RAISE(FAIL, 'simulated disk failure'); END""")
    collector.store.db.commit()
    message = HouseSimulation(node_count=1).history[0]
    packet = SimpleNamespace(topic=telemetry_topic(message["device_id"]),
                             payload=json.dumps(message).encode(), retain=False, qos=1, mid=1)
    acknowledgements = []
    client = SimpleNamespace(ack=lambda *args: acknowledgements.append(args))
    try:
        with pytest.raises(sqlite3.Error):
            collector._message(client, None, packet)
        assert not acknowledgements
        assert collector.counts["stored"] == 0 and collector.counts["storage_errors"] == 1
        assert collector.store.db.execute("SELECT count(*) FROM telemetry").fetchone()[0] == 0
    finally:
        collector.close()


def test_failed_publisher_preserves_run_manifest(tmp_path, monkeypatch):
    import simulator.mqtt as publisher
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["mqtt", "--run-id", "failed-run", "--steps", "1"])
    def fail(self):
        raise ConnectionError("Broker not available")
    monkeypatch.setattr(Connection, "connect", fail)
    assert publisher.main() == 1
    archive = json.loads((tmp_path / "experiments/runs/failed-run-mqtt.json").read_text())
    assert archive["transport"] == {"status": "failed", "broker_acked": 0,
                                     "collector_delivery": "unverified"}
    assert archive["manifest"]["run_id"] == "failed-run"
    with pytest.raises(SystemExit) as existing:
        publisher.main()
    assert existing.value.code == 2


def test_mqtt_control_changes_telemetry_stored_by_collector(receiver, sender, broker):
    from uuid import uuid4
    from contracts.commands import command_topic, decode_result, result_topic
    from simulator.control import CommandReceiver
    from simulator.telemetry import session_id
    sim = HouseSimulation(node_count=1, extra_nodes=1)
    connection = Connection(broker.port)
    control = CommandReceiver(sim, connection)
    replies = []
    sender.client.on_message = lambda client, userdata, packet: replies.append(
        decode_result(packet.payload, topic=packet.topic))
    node = "esp32_node_01"
    command = {"schema_version": "1.0", "command_id": str(uuid4()), "device_id": node,
               "target_boot_id": session_id(sim.run_id, node), "component_id": "led_01",
               "operation": "set", "value": 1, "observed_uptime_ms": 0, "expires_uptime_ms": 5000}
    try:
        control.connect()
        sender.subscribe([result_topic(node)])
        control.publish_telemetry()
        sender.publish(command_topic(node), json.dumps(command).encode())
        def responded():
            control.service()
            sender.pump()
            return bool(replies)
        wait_until(responded)
        assert replies[0]["status"] == "accepted"
        sender.publish(command_topic(node), json.dumps(command).encode())
        def received_repeat():
            control.service()
            sender.pump()
            return len(replies) == 2
        wait_until(received_repeat)
        sender.publish(command_topic(node), json.dumps({**command, "value": 0}).encode())
        def received_conflict():
            control.service()
            sender.pump()
            return len(replies) == 3
        wait_until(received_conflict)
        assert replies[0] == replies[1]
        assert replies[2]["reason"] == "duplicate_conflict"
        assert len(sim.actions) == 1
        sim.step()
        control.publish_telemetry()
        wait_until(lambda: receiver.count() == 4)
        wait_until(lambda: receiver.collector.counts["control_stored"] == 6)
        with sqlite3.connect(receiver.database) as db:
            reports = [json.loads(row[0]) for row in db.execute(
                "SELECT payload FROM telemetry WHERE device_id=? ORDER BY sequence_number", (node,))]
        assert [r["actuators"]["led_01"]["commanded"] for r in reports] == [0, 1]
        assert receiver.collector.counts["conflict"] == 0
        from fastapi.testclient import TestClient
        from edge.api import create_app
        with TestClient(create_app(receiver.database)) as api:
            page = api.get(f"/devices/{node}/control-history",
                           params={"command_id": command["command_id"]}).json()
        commands = [r for r in page["items"] if r["kind"] == "command"]
        results = [r for r in page["items"] if r["kind"] == "result"]
        assert [r["message"]["value"] for r in commands] == [1, 1, 0]
        assert [r["message"]["status"] for r in results] == ["accepted", "accepted", "rejected"]
        assert len({r["id"] for r in page["items"]}) == 6
    finally:
        connection.close()


def test_control_collector_resubscribes_and_preserves_receipts_after_restart(receiver, sender, broker):
    from uuid import uuid4
    from contracts.commands import command_topic, result_topic
    report = HouseSimulation(node_count=1).history[0]
    node = report["device_id"]
    command = {"schema_version": "1.0", "command_id": str(uuid4()), "device_id": node,
               "target_boot_id": report["boot_id"], "component_id": "led_01", "operation": "set",
               "value": 1, "observed_uptime_ms": 0, "expires_uptime_ms": 5000}
    result = {"schema_version": "1.0", "command_id": command["command_id"], "device_id": node,
              "boot_id": report["boot_id"], "component_id": "led_01", "status": "accepted",
              "reason": None, "handled_uptime_ms": 0}
    sender.publish(command_topic(node), json.dumps(command).encode())
    wait_until(lambda: receiver.collector.counts["control_stored"] == 1)
    broker.stop()
    wait_until(lambda: receiver.collector.counts["disconnects"] > 0)
    broker.start()
    wait_until(lambda: receiver.collector.counts["connections"] >= 2 and receiver.collector.ready)
    replacement = Connection(broker.port)
    try:
        replacement.connect()
        replacement.publish(command_topic(node), json.dumps(command).encode())
        replacement.publish(result_topic(node), json.dumps(result).encode())
        wait_until(lambda: receiver.collector.counts["control_stored"] == 3)
        with sqlite3.connect(receiver.database) as db:
            receipts = db.execute("SELECT kind, collector_session_id FROM control_observations ORDER BY id").fetchall()
        assert [r[0] for r in receipts] == ["command", "command", "result"]
        assert len({r[1] for r in receipts}) == 1  # Broker restart does not restart the collector clock.
    finally:
        replacement.close()
