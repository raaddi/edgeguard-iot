import json

import pytest

from ml.gate_split import load_sessions, main, split_sessions
from simulator.gate_pilot import run_suite


def test_related_profiles_and_faults_stay_in_one_partition(tmp_path):
    roots = [run_suite(output=tmp_path, suite_id=p, profile=p) for p in ("standard", "repeat_open")]
    sessions = load_sessions(roots)
    split = split_sessions(sessions)
    assert split == split_sessions(list(reversed(sessions)))
    parts = split["partitions"]
    assert {k: len(v) for k, v in parts.items()} == {
        "train": 2, "validation": 8, "test": 8, "excluded_train_faults": 6}
    assert all(s["case"] == "normal" for s in parts["train"])
    memberships = {}
    for partition, rows in parts.items():
        for row in rows:
            memberships.setdefault(row["paired_group"], set()).add(
                "train" if partition == "excluded_train_faults" else partition)
    assert all(len(names) == 1 for names in memberships.values())
    assert len({s["run_id"] for rows in parts.values() for s in rows}) == len(sessions)
    with pytest.raises(ValueError, match="Duplicate"):
        split_sessions(sessions + sessions)


def test_reject_small_incomplete_duplicate_or_corrupt_inputs(tmp_path):
    root = run_suite(output=tmp_path, sessions_per_case=1)
    with pytest.raises(ValueError, match="three"):
        split_sessions(load_sessions([root]))
    with pytest.raises(ValueError, match="duplicate"):
        load_sessions([root, root])
    path = root / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["status"] = "failed"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="completed"):
        load_sessions([root])
    manifest["status"] = "completed"
    manifest["sessions"][0]["run_id"] = "../outside"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        load_sessions([root])


def test_cli_persists_plan_and_refuses_overwrite(tmp_path, monkeypatch):
    root = run_suite(output=tmp_path)
    output = root / "split.json"
    monkeypatch.setattr("sys.argv", ["gate_split", str(root), "--output", str(output)])
    assert main() == 0
    before = output.read_bytes()
    result = json.loads(before)
    assert result["partitions"]["train"] and result["source_suites"] == [str(root.resolve())]
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1 and output.read_bytes() == before
