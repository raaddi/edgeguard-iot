import json

import pytest

from ml.gate_experiment import run_experiment


def test_complete_experiment_freezes_training_then_evaluates(tmp_path):
    root = tmp_path / "experiment"
    report = run_experiment(root, groups=5)
    manifest = json.loads((root / "manifest.json").read_text())
    split = json.loads((root / "split.json").read_text())
    assert manifest["status"] == "completed"
    assert {p.name for p in (root / "raw").iterdir()} == {
        "standard-seed-42", "repeat_open-seed-42", "early_return-seed-42", "idle-seed-42"}
    assert report["calibration"]["training_rows"] == 12 * 161
    assert report["calibration"]["normal_validation_rows"] == 4 * 161
    assert all(s["case"] == "normal" for s in split["partitions"]["train"])
    assert set(report["partitions"]) == {"validation", "test"}
    for name, result in report["partitions"]["test"].items():
        r = result["overall"]
        assert r["events"] > 0 and r["normal_duration_ms"] == 32000
        assert r["detected_events"] + r["missed_events"] == r["events"]
        assert len(r["detection_delays_ms"]) == r["detected_events"]
        # No assertion that ML beats the baseline: negative results are valid.
        assert result["by_case"]["normal"]["events"] == 0
    assert (root / "detectors.joblib").is_file() and (root / "report.md").is_file()
    assert len(list((root / "predictions").glob("*.json"))) == 32
    first = next((root / "predictions").glob("*.json"))
    assert "labels" not in json.loads(first.read_text())
    with pytest.raises(FileExistsError):
        run_experiment(root, groups=5)


def test_experiment_failure_is_not_reported_as_complete(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("test generator failure")
    monkeypatch.setattr("ml.gate_experiment.run_suite", fail)
    with pytest.raises(ValueError):
        run_experiment(tmp_path / "failed", groups=5)
    assert json.loads((tmp_path / "failed" / "manifest.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("kwargs", [{"groups": 4}, {"groups": 26}, {"seed": -1}])
def test_invalid_configuration_does_not_create_output(tmp_path, kwargs):
    with pytest.raises(ValueError):
        run_experiment(tmp_path / "invalid", **kwargs)
    assert not (tmp_path / "invalid").exists()
