"""Contract boundary: malformed input, hardware semantics and producer compatibility."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from contracts.telemetry import (
    MAX_PAYLOAD_BYTES, TelemetryError, decode_telemetry, telemetry_topic, validate_telemetry,
)
from simulator.house import HouseSimulation
from simulator.telemetry import build_message, session_id

ROOT = Path(__file__).resolve().parents[1]


def example():
    return json.loads((ROOT / "contracts/examples/physical-node.json").read_text(encoding="utf-8"))


def test_physical_example_preserves_zero_missing_feedback_and_unsynced_time():
    message = example()
    result = decode_telemetry(json.dumps(message).encode(), topic=telemetry_topic(message["device_id"]))
    assert result == message
    assert result["sensors"]["gas_01"]["value"] == 0
    assert result["sensors"]["gas_02"]["value"] is None
    assert result["actuators"]["servo_01"]["reported"] is None


@pytest.mark.parametrize("path,value", [
    (("schema_version",), "0.2-draft"),
    (("device_id",), "node/other"),
    (("device_id",), "node\n"),
    (("boot_id",), "not-a-uuid"),
    (("sequence_number",), -1),
    (("sequence_number",), True),
    (("sequence_number",), 4294967296),
    (("uptime_ms",), -1),
    (("timestamp",), "2026-02-30T12:00:00Z"),
    (("timestamp",), "2026-01-01T12:00:00"),
    (("timestamp",), "2026-01-01T12:00:00+02:00"),
    (("sensors", "gas_01", "value"), None),
    (("sensors", "gas_01", "value"), True),
    (("sensors", "gas_01", "value"), 1.1),
    (("sensors", "gas_01", "value"), float("nan")),
    (("sensors", "gas_01", "value"), float("inf")),
    (("sensors", "gas_02", "value"), 0),
    (("sensors", "gas_01", "unit"), "ppm"),
    (("actuators", "servo_01", "reported"), 110),
    (("actuators", "servo_01", "commanded"), 181),
    (("actuators", "fan_01", "reported"), None),
    (("actuators", "fan_01", "commanded"), 2),
    (("actuators", "fan_01", "unit"), "degrees"),
    (("scenario_ground_truth",), "gas_spike"),
    (("sensors", "gas_01", "environment"), 0.7),
])
def test_rejects_incompatible_or_misleading_fields(path, value):
    message = example()
    target = message
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(TelemetryError):
        validate_telemetry(message)


@pytest.mark.parametrize("payload", [
    b'{"device_id":"a","device_id":"b"}', b'{"x":NaN}', b'{"x":Infinity}',
    b'{"x":1e999}', b'\xff', b'[]', b'null', b'{',
    b' ' * (MAX_PAYLOAD_BYTES + 1), b'[' * 2000 + b']' * 2000,
], ids=["duplicate-key", "nan", "infinity", "overflow", "invalid-utf8",
        "array", "null", "malformed", "oversized", "deeply-nested"])
def test_strict_bounded_wire_decoding(payload):
    with pytest.raises(TelemetryError):
        decode_telemetry(payload)


def test_component_limits_identity_and_required_fields():
    message = example()
    with pytest.raises(TelemetryError, match="Topic"):
        decode_telemetry(json.dumps(message).encode(), topic=telemetry_topic("other_node"))
    for change in ("missing", "collision", "too_many", "invalid_id"):
        changed = deepcopy(message)
        if change == "missing":
            del changed["sensors"]
        elif change == "collision":
            changed["sensors"]["fan_01"] = changed["sensors"]["gas_01"]
        elif change == "invalid_id":
            changed["sensors"]["gas_01\n"] = changed["sensors"].pop("gas_01")
        else:
            changed["sensors"] = {f"gas_{i}": message["sensors"]["gas_01"] for i in range(65)}
        with pytest.raises(TelemetryError):
            validate_telemetry(changed)


@pytest.mark.parametrize("nodes", [1, 2, 3])
def test_both_producers_use_one_contract_across_scenarios(nodes):
    single = build_message("virtual_node_01", session_id("fixture", "virtual_node_01"), 0, 0.2)
    house = HouseSimulation(node_count=nodes, extra_nodes=2)
    house.inject("gas_spike", "gas_01", 3)
    house.inject("fan_failure", "fan_01", 3)
    house.inject("sensor_freeze", "gas_02", 2)
    house.inject("node_offline", "virtual_node_01", 2)
    for _ in range(4):
        house.step()
    for message in [single, *house.history]:
        validate_telemetry(message, topic=telemetry_topic(message["device_id"]))
        assert message["schema_version"] == "1.0"
        assert message["uptime_ms"] == message["sequence_number"] * 1000
    assert single["actuators"] == {}
    fan_messages = [m["actuators"]["fan_01"] for m in house.history if "fan_01" in m["actuators"]]
    assert any(s["commanded"] == 1 and s["reported"] == 0 and s["feedback"] == "simulated" for s in fan_messages)


def test_validator_cli_accepts_jsonl_and_reports_bad_line(tmp_path):
    message = build_message("node_01", session_id("fixture", "node_01"), 0, 0.2)
    path = tmp_path / "telemetry.jsonl"
    path.write_text(json.dumps(message) + "\n", encoding="utf-8")
    command = [sys.executable, "-m", "contracts", str(path)]
    good = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert good.returncode == 0
    assert "Validated 1" in good.stdout
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"invalid": true}\n')
    bad = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15)
    assert bad.returncode == 1
    assert "line 2" in bad.stderr


def test_replay_refuses_old_model_instead_of_silently_reinterpreting_it():
    exported = HouseSimulation().export()
    exported["manifest"]["model"] = "house-behaviour-v1"
    with pytest.raises(ValueError, match="Unsupported replay"):
        HouseSimulation.replay(exported)
