import hashlib
import json
from pathlib import Path

import pytest

from ml.gate_sequence_export import export_sequences
from ml.gate_split import load_sessions, split_sessions
from simulator.gate_pilot import run_suite


def setup_plan(tmp_path, **kwargs):
    root = run_suite(output=tmp_path, suite_id="pilot", **kwargs)
    plan = split_sessions(load_sessions([root]))
    path = root / "split.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return root, path, plan


def test_export_preserves_partitions_provenance_and_ignores_fault_labels(tmp_path):
    root, path, plan = setup_plan(tmp_path)
    for truth in root.glob("*/ground_truth.json"):
        truth.write_text("not an input to forecasting", encoding="utf-8")
    output = tmp_path / "sequences"
    result = export_sequences(path, output)
    assert result["status"] == "completed" and result["examples"] == 9 * 141
    assert result["excluded_sessions"] == 3
    assert (output / "source-split.json").read_bytes() == path.read_bytes()
    assert result["split_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert not (output / "excluded_train_faults").exists()
    for name in ("train", "validation", "test"):
        assert {p.stem for p in (output / name).glob("*.jsonl")} == {
            s["run_id"] for s in plan["partitions"][name]}
    for entry in result["sessions"]:
        file = output / entry["partition"] / (entry["run_id"] + ".jsonl")
        assert hashlib.sha256(file.read_bytes()).hexdigest() == entry["sequences_sha256"]
        rows = [json.loads(line) for line in file.read_text().splitlines()]
        assert rows[0]["prediction_ms"] == 950 and rows[-1]["target_ms"] == 8000
        assert all(set(r) == {"input_times_ms", "prediction_ms", "target_ms", "x", "y", "persistence"}
                   for r in rows)
        assert all(r["persistence"] == {k: r["x"][-1][k] for k in r["y"]} for r in rows)
    report = json.loads((output / "persistence-report.json").read_text())
    assert set(report["partitions"]["train"]["by_case"]) == {"normal"}
    assert report["partitions"]["validation"]["overall"]["examples"] == 4 * 141
    before = (output / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        export_sequences(path, output)
    assert (output / "manifest.json").read_bytes() == before


def test_longer_horizon_missing_current_and_repeatable_output(tmp_path):
    _, path, _ = setup_plan(tmp_path, measure_current=False)
    first, second = tmp_path / "first", tmp_path / "second"
    for output in (first, second):
        result = export_sequences(path, output, horizon_samples=5)
        assert result["examples"] == 9 * 137
    for file in first.rglob("*.jsonl"):
        assert file.read_bytes() == (second / file.relative_to(first)).read_bytes()
    report = json.loads((first / "persistence-report.json").read_text())
    current = report["partitions"]["train"]["overall"]["channels"]["current_a"]
    assert current["pairs"] == 0 and current["mae_a"] is None
    assert current["missing_target"] == current["missing_prediction"] == 137


def test_tampered_split_creates_no_output(tmp_path):
    _, path, plan = setup_plan(tmp_path)
    plan["partitions"]["train"].append(plan["partitions"]["test"].pop())
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="assignment"):
        export_sequences(path, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_mixed_session_marks_export_failed(tmp_path):
    _, path, plan = setup_plan(tmp_path)
    source = Path(plan["partitions"]["train"][0]["path"]) / "observations.jsonl"
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    rows[-1]["run_id"] = "other"
    source.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    output = tmp_path / "failed"
    with pytest.raises(ValueError, match="Mixed"):
        export_sequences(path, output)
    assert json.loads((output / "manifest.json").read_text())["status"] == "failed"
    assert not (output / "persistence-report.json").exists()


def test_example_budget_stops_export_and_invalid_config_creates_no_output(tmp_path, monkeypatch):
    _, path, _ = setup_plan(tmp_path)
    output = tmp_path / "bounded"
    with pytest.raises(ValueError, match="history_samples"):
        export_sequences(path, output, history_samples=True)
    assert not output.exists()
    monkeypatch.setattr("ml.gate_sequence_export.MAX_EXAMPLES", 1)
    with pytest.raises(ValueError, match="forecast examples"):
        export_sequences(path, output)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["status"] == "failed" and manifest["examples"] == 1
