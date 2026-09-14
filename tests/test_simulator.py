"""Check repeatable data, logical time and the command-line boundary."""

from datetime import datetime, timedelta
from itertools import islice
import json
from pathlib import Path
import subprocess
import sys

import pytest

from simulator.normal_activity import gas_signal

ROOT = Path(__file__).resolve().parents[1]


def run_simulator(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "simulator", *arguments],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
    )


def test_signal_is_repeatable_variable_and_bounded():
    first = list(islice(gas_signal(42), 10_000))
    assert first == list(islice(gas_signal(42), 10_000))
    assert first != list(islice(gas_signal(43), 10_000))
    assert len(set(first)) > 1
    assert all(0 <= value <= 1 for value in first)


def test_cli_separates_metadata_and_preserves_logical_time():
    first = run_simulator("--samples", "3", "--device-id", "my_node")
    second = run_simulator("--samples", "3", "--device-id", "my_node")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    messages = [json.loads(line) for line in first.stdout.splitlines()]
    manifest = json.loads(first.stderr)
    assert len(messages) == 3
    assert manifest["source"] == "synthetic"
    assert manifest["scenario_schedule"] == []
    assert manifest["seed"] == 42
    start = datetime.fromisoformat(manifest["logical_start"])
    for index, message in enumerate(messages):
        assert message["device_id"] == "my_node"
        assert message["boot_id"] == manifest["boot_id"]
        assert message["sequence_number"] == index
        assert datetime.fromisoformat(message["timestamp"]) == start + timedelta(seconds=index)
        assert message["sensors"][manifest["sensor_id"]]["unit"] == "normalized"
        assert "source" not in message
        assert "scenario_schedule" not in message


def test_new_run_has_distinct_session_identity():
    first = run_simulator("--run-id", "experiment-a", "--samples", "1")
    second = run_simulator("--run-id", "experiment-b", "--samples", "1")
    assert first.returncode == second.returncode == 0
    assert json.loads(first.stdout)["boot_id"] != json.loads(second.stdout)["boot_id"]


@pytest.mark.parametrize("arguments", [
    ["--samples", "0"], ["--samples", "-1"], ["--samples", "100001"],
    ["--samples", "abc"], ["--device-id", "bad/+/id"], ["--run-id", ""],
])
def test_cli_rejects_invalid_configuration_before_emitting_data(arguments):
    result = run_simulator(*arguments)
    assert result.returncode == 2
    assert result.stdout == ""
