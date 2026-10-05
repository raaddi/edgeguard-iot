import json
from pathlib import Path
import subprocess
import sys

import pytest

from ml import gate_response_export as exporter
from ml.gate_features import extract_features
from simulator.gate_research_suite import CONDITIONS, CALIBRATION_CONDITIONS


def reduced_roles(monkeypatch):
    monkeypatch.setattr(exporter, "ROLE_SEEDS", {
        "train": (3000,), "selection": (4000,),
        "calibration": (5000,), "evaluation": (6000,),
    })


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_default_protocol_has_frozen_440_sessions_and_historical_disjointness():
    assert exporter._validate_roles() == 440
    assert exporter.ROLE_SEEDS["train"] == tuple(range(3000, 3016))
    assert exporter.ROLE_SEEDS["selection"] == tuple(range(4000, 4008))
    assert exporter.ROLE_SEEDS["calibration"] == tuple(range(5000, 5016))
    assert exporter.ROLE_SEEDS["evaluation"] == tuple(range(6000, 6016))
    assert set(CALIBRATION_CONDITIONS) == {"cycles", "repeats", "idle"}
    assert set(CONDITIONS) == {"cycles", "repeats", "idle", "slow", "reversals"}
    assert all(settings.duration_ms == 30000 for settings in CONDITIONS.values())


def test_export_preserves_roles_provenance_and_true_causal_inputs(tmp_path, monkeypatch):
    reduced_roles(monkeypatch)
    output = tmp_path / "responses"
    result = exporter.export_responses(output)
    assert result["status"] == "completed" and len(result["sessions"]) == 29
    assert result["expected_sessions"] == 29
    assert result["response_version"] == "gate-command-response-1"
    assert result["seed_roles"] == exporter.ROLE_SEEDS
    assert result["group_assignments"] == {"3000": "train", "4000": "selection",
                                           "5000": "calibration", "6000": "evaluation"}
    assert (output / "protocol.md").read_bytes() == exporter.PROTOCOL_PATH.read_bytes()
    assert result["protocol_sha256"] == exporter.digest(output / "protocol.md")
    assert result["report_sha256"] == exporter.digest(output / "report.json")
    expected = {"train": 3, "selection": 3, "calibration": 3, "evaluation": 20}
    for role, count in expected.items():
        assert len(list((output / "examples" / role).glob("*.json"))) == count
    for entry in result["sessions"]:
        assert entry["seed"] in exporter.ROLE_SEEDS[entry["role"]]
        assert entry["paired_group"] == f"gate-v1-seed-{entry['seed']}"
        if entry["role"] != "evaluation":
            assert entry["case"] == "normal" and entry["condition"] in CALIBRATION_CONDITIONS
        for name in ("observations", "events", "ground_truth", "examples"):
            assert exporter.digest(output / entry[name + "_file"]) == entry[name + "_sha256"]
        data = read(output / entry["examples_file"])
        obs = rows(output / entry["observations_file"])
        events = rows(output / entry["events_file"])
        features = {row["logical_ms"]: row["x"] for row in extract_features(obs, events)}
        sent = {event["message"]["command_id"]: event for event in events
                if event["kind"] == "command_sent"}
        assert len(sent) == entry["commands"] == len(data["examples"]) + len(data["excluded"])
        assert not data["excluded"]
        for example in data["examples"]:
            now = example["prediction_ms"]
            assert example["command_id"] in sent and sent[example["command_id"]]["logical_ms"] == now
            assert example["input_times_ms"] == list(range(now - 950, now + 1, 50))
            assert example["x"] == [features[time] for time in example["input_times_ms"]]
            assert example["x"][-1]["last_command_degrees"] == example["target_degrees"]
            assert all(not {"seed", "case", "config", "ground_truth", "command_id", "y"}.intersection(x)
                       for x in example["x"])
            for name in ("ack", "contact"):
                target = example["y"][name]
                assert target["duration_ms"] is not None if target["observed"] else target["duration_ms"] is None
                assert target["censor_reason"] is None if target["observed"] else target["censor_reason"] is not None
    report = read(output / "report.json")
    assert report["overall"]["sessions"] == 29
    assert report["overall"]["commands"] == result["commands"] == result["examples"]
    assert report["overall"]["excluded"] == result["excluded"] == 0
    assert len(report["sessions"]) == 29
    for role in ("train", "selection", "calibration"):
        assert set(report["by_role"][role]["by_case"]) == {"normal"}
        assert set(report["by_role"][role]["by_condition"]) == set(CALIBRATION_CONDITIONS)
    assert set(report["by_role"]["evaluation"]["by_case"]) == set(exporter.CASES)
    assert set(report["by_role"]["evaluation"]["by_condition"]) == set(CONDITIONS)
    assert report["by_case"]["motion_stall"]["contact"]["censored"] > 0
    assert report["by_case"]["open_contact_stuck_low"]["contact"]["censored"] > 0
    for name in ("ack", "contact"):
        stats = report["overall"][name]
        assert stats["observed"] + stats["censored"] == result["examples"]
        assert sum(stats["censor_reasons"].values()) == stats["censored"]
    before = (output / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        exporter.export_responses(output)
    assert (output / "manifest.json").read_bytes() == before


def test_repeated_export_has_identical_raw_data_examples_and_report(tmp_path, monkeypatch):
    reduced_roles(monkeypatch)
    first, second = tmp_path / "first", tmp_path / "second"
    exporter.export_responses(first)
    exporter.export_responses(second)
    for folder in ("raw", "examples"):
        for file in (first / folder).rglob("*"):
            if file.is_file():
                assert file.read_bytes() == (second / file.relative_to(first)).read_bytes()
    assert (first / "report.json").read_bytes() == (second / "report.json").read_bytes()


@pytest.mark.parametrize("replacement", [
    {"train": (42,), "selection": (4000,), "calibration": (5000,), "evaluation": (6000,)},
    {"train": (1000,), "selection": (4000,), "calibration": (5000,), "evaluation": (6000,)},
    {"train": (2000,), "selection": (4000,), "calibration": (5000,), "evaluation": (6000,)},
    {"train": (3000,), "selection": (3000,), "calibration": (5000,), "evaluation": (6000,)},
    {"train": (3000, 3000), "selection": (4000,), "calibration": (5000,), "evaluation": (6000,)},
    {"train": (True,), "selection": (4000,), "calibration": (5000,), "evaluation": (6000,)},
    {"train": (), "selection": (4000,), "calibration": (5000,), "evaluation": (6000,)},
    {"train": (3000,), "selection": (4000,), "calibration": (5000,), "evaluation": (-1,)},
    {"train": (3000,), "selection": (4000,), "calibration": (5000,), "evaluation": (2**32,)},
    {"train": (3000,), "selection": (4000,), "calibration": (5000,)},
])
def test_invalid_or_overlapping_seed_roles_create_no_output(tmp_path, monkeypatch, replacement):
    monkeypatch.setattr(exporter, "ROLE_SEEDS", replacement)
    output = tmp_path / "invalid"
    with pytest.raises(ValueError, match="seed|Seed"):
        exporter.export_responses(output)
    assert not output.exists()


def test_generation_failure_preserves_failed_manifest_and_prior_hashes(tmp_path, monkeypatch):
    reduced_roles(monkeypatch)
    simulate = exporter.simulate_session
    calls = 0
    def fail_second(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("Controlled export failure")
        return simulate(**kwargs)
    monkeypatch.setattr(exporter, "simulate_session", fail_second)
    output = tmp_path / "failed"
    with pytest.raises(ValueError, match="Controlled"):
        exporter.export_responses(output)
    manifest = read(output / "manifest.json")
    assert manifest["status"] == "failed" and len(manifest["sessions"]) == 1
    assert manifest["protocol_sha256"] == exporter.digest(output / "protocol.md")
    entry = manifest["sessions"][0]
    assert entry["examples_sha256"] == exporter.digest(output / entry["examples_file"])
    assert not (output / "report.json").exists()


def test_incomplete_command_accounting_marks_export_failed(tmp_path, monkeypatch):
    reduced_roles(monkeypatch)
    monkeypatch.setattr(exporter, "extract_response_examples", lambda *args, **kwargs: {
        "response_version": "gate-command-response-1", "examples": [], "excluded": [],
    })
    output = tmp_path / "failed"
    with pytest.raises(ValueError, match="account"):
        exporter.export_responses(output)
    assert read(output / "manifest.json")["status"] == "failed"
    assert not (output / "report.json").exists()


def test_missing_protocol_or_session_budget_creates_no_output(tmp_path, monkeypatch):
    reduced_roles(monkeypatch)
    monkeypatch.setattr(exporter, "PROTOCOL_PATH", tmp_path / "missing.md")
    with pytest.raises(FileNotFoundError):
        exporter.export_responses(tmp_path / "missing")
    assert not (tmp_path / "missing").exists()
    monkeypatch.setattr(exporter, "MAX_SESSIONS", 1)
    with pytest.raises(ValueError, match="budget"):
        exporter.export_responses(tmp_path / "too-many")
    assert not (tmp_path / "too-many").exists()


def test_export_import_needs_no_ml_or_gui_libraries():
    root = Path(__file__).resolve().parents[1]
    script = """
import importlib.abc
import sys
blocked = {'torch', 'numpy', 'sklearn', 'joblib', 'PySide6'}
class NoHeavyLibraries(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in blocked:
            raise AssertionError('Exporter imported an ML/GUI dependency: ' + fullname)
sys.meta_path.insert(0, NoHeavyLibraries())
import ml.gate_response_export
import simulator.gate_research_suite
assert not any(name.split('.')[0] in blocked for name in sys.modules)
print('stdlib and shared contract dependencies only')
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=root, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "shared contract" in result.stdout
