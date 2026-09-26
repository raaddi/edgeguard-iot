import hashlib
import json

import pytest

from ml.gate_feature_export import export_features
from ml.gate_split import load_sessions, split_sessions
from simulator.gate_pilot import run_suite


def make_plan(tmp_path):
    root = run_suite(output=tmp_path, suite_id="pilot")
    plan = split_sessions(load_sessions([root]))
    path = root / "split.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return root, path, plan


def test_export_respects_split_and_has_no_truth_dependency(tmp_path):
    root, path, plan = make_plan(tmp_path)
    # If this file were used as a feature input, this test would fail.
    for truth in root.glob("*/ground_truth.json"):
        truth.write_text("not JSON: labels are not feature inputs", encoding="utf-8")
    output = tmp_path / "features"
    result = export_features(path, output)
    assert result["status"] == "completed" and len(result["feature_names"]) == 20
    assert len(result["sessions"]) == 9 and result["excluded_sessions"] == 3
    assert result["split_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert (output / "source-split.json").read_bytes() == path.read_bytes()
    assert not (output / "excluded_train_faults").exists()
    for partition in ("train", "validation", "test"):
        assert {p.stem for p in (output / partition).glob("*.jsonl")} == {
            s["run_id"] for s in plan["partitions"][partition]}
        for file in (output / partition).glob("*.jsonl"):
            rows = [json.loads(line) for line in file.read_text().splitlines()]
            assert len(rows) == 161 and rows[0]["x"]["last_command_degrees"] is None
            assert all(set(r) == {"logical_ms", "x"} for r in rows)
            assert all(list(r["x"]) == result["feature_names"] for r in rows)
    before = (output / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        export_features(path, output)
    assert (output / "manifest.json").read_bytes() == before


def test_tampered_split_is_rejected_before_output(tmp_path):
    _, path, plan = make_plan(tmp_path)
    plan["partitions"]["train"].append(plan["partitions"]["test"].pop())
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="assignment"):
        export_features(path, tmp_path / "features")
    assert not (tmp_path / "features").exists()


@pytest.mark.parametrize("bad", ["nan", "duplicate_key", "wrong_run"])
def test_bad_observation_marks_export_failed(tmp_path, bad):
    _, path, plan = make_plan(tmp_path)
    from pathlib import Path
    file = Path(plan["partitions"]["train"][0]["path"]) / "observations.jsonl"
    lines = file.read_text().splitlines()
    row = json.loads(lines[0])
    if bad == "nan": row["current_a"] = float("nan")
    if bad == "wrong_run": row["run_id"] = "wrong"
    lines[0] = json.dumps(row)
    if bad == "duplicate_key": lines[0] = lines[0][:-1] + ', "logical_ms": 0}'
    file.write_text("\n".join(lines) + "\n")
    output = tmp_path / "features"
    with pytest.raises(ValueError):
        export_features(path, output)
    assert json.loads((output / "manifest.json").read_text())["status"] == "failed"
