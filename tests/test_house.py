"""Behaviour, data boundaries and reproducibility of the SmartHome model."""

import json
from collections import Counter
import pytest
from simulator.house import HouseSimulation, load_profile


def test_reference_profile_and_configurable_nodes():
    sim = HouseSimulation(node_count=1, extra_nodes=2)
    assert Counter(c["kind"] for c in sim.components.values()) == {"light": 10, "servo": 6, "gas": 6, "fan": 4}
    assert len(sim.nodes) == 3
    other = HouseSimulation(node_count=3)
    for _ in range(20):
        sim.step()
        other.step()
    # Moving components between nodes or adding independent nodes cannot change their readings.
    assert sim.sensors["gas_01"]["value"] == other.sensors["gas_01"]["value"]
    assert sim.sensors["gas_01"]["value"] != sim.sensors["gas_02"]["value"]


def test_gas_rule_failure_recovery_and_freeze():
    sim = HouseSimulation()
    sim.inject("gas_spike", "gas_01", 3)
    sim.inject("fan_failure", "fan_01", 2)
    sim.step()
    assert sim.actuators["fan_01"]["commanded"] == 1
    assert sim.actuators["fan_01"]["simulated"] == 0
    assert {a["rule"] for a in sim.alerts} == {"gas_threshold", "actuator_mismatch"}
    sim.step()
    sim.step()
    assert sim.actuators["fan_01"]["simulated"] == 1
    for _ in range(40):
        sim.step()
    assert sim.actuators["fan_01"]["simulated"] == 0
    frozen = sim.sensors["gas_01"]["value"]
    sim.inject("sensor_freeze", "gas_01", 3)
    sim.inject("gas_spike", "gas_01", 3)
    sim.step()
    assert sim.sensors["gas_01"]["value"] == frozen
    assert sim.sensors["gas_01"]["environment"] > frozen
    assert sim.actuators["fan_01"]["commanded"] == 0


def test_offline_suppresses_messages_and_commands_but_not_local_rules():
    sim = HouseSimulation(node_count=1)
    sim.inject("node_offline", "esp32_node_01", 2)
    sim.inject("gas_spike", "gas_01", 2)
    sim.step()
    assert len(sim.history) == 1
    assert sim.suppressed_messages == 1
    assert sim.actuators["fan_01"]["simulated"] == 1
    assert sim.command("led_01", 1) is False
    assert sim.actuators["led_01"]["simulated"] == 0
    sim.step()
    sim.step()
    assert sim.history[-1]["sequence_number"] == 3


def test_export_is_reproducible_and_ground_truth_is_separate():
    sim = HouseSimulation(extra_nodes=2)
    sim.command("led_01", 1)
    sim.command("servo_01", 110)
    sim.inject("gas_spike", "gas_01", 4)
    sim.inject("sensor_freeze", "gas_02", 2)
    for _ in range(5):
        sim.step()
    sim.command("fan_01", 0)
    sim.auto_fan("fan_01")
    payload = json.loads(json.dumps(sim.export({"commit": "fixture"})))
    replay = HouseSimulation.replay(payload)
    assert replay.export({"commit": "fixture"}) == payload
    for message in payload["telemetry"]:
        assert "scenario" not in json.dumps(message)
        assert "environment" not in json.dumps(message)
    last = next(m for m in reversed(sim.history) if "led_01" in m["actuators"])
    previous = last["actuators"]["led_01"]["reported"]
    sim.command("led_01", 0)
    assert last["actuators"]["led_01"]["reported"] == previous


def test_limits_and_invalid_configuration():
    sim = HouseSimulation()
    for _ in range(1050):
        sim.step()
    assert len(sim.history) == sim.HISTORY_LIMIT
    assert sim.evicted_messages == sim.message_count - sim.HISTORY_LIMIT
    with pytest.raises(ValueError):
        sim.inject("gas_spike", "led_01")
    with pytest.raises(ValueError):
        sim.command("servo_01", 999)
    profile = load_profile()
    profile["components"].append(profile["components"][0])
    with pytest.raises(ValueError):
        HouseSimulation(profile=profile)
