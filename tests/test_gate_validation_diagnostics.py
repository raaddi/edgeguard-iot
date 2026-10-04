import json

import pytest

pytest.importorskip("torch")

from ml.gate_alarm_experiment import run_experiment
from ml.gate_forecast_data import SequenceDataset
from ml.gate_validation_diagnostics import run_diagnostics
from test_gate_alarm_experiment import inputs


def test_diagnostics_only_read_validation_and_preserve_frozen_inputs(inputs, tmp_path, monkeypatch):
    sequences, gru = inputs
    comparison = tmp_path / "alarms"
    run_experiment(sequences, gru, comparison)
    before = {p: p.read_bytes() for p in (gru / "weights.pt", comparison / "calibration.json")}
    original = SequenceDataset.sessions
    partitions = []

    def checked(self, partition, **kwargs):
        partitions.append(partition)
        assert partition == "validation"
        yield from original(self, partition, **kwargs)

    monkeypatch.setattr(SequenceDataset, "sessions", checked)
    output = tmp_path / "diagnostics"
    report = run_diagnostics(sequences, gru, comparison, output)
    assert partitions == ["validation"]
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert report["persistence_sensitivity"]["3"]["overall"]["events"] == len(report["events"])
    assert json.loads((output / "manifest.json").read_text())["status"] == "completed"
    assert len(list((output / "timelines").glob("*.json"))) == 4
    with pytest.raises(FileExistsError):
        run_diagnostics(sequences, gru, comparison, output)


def test_changed_calibration_is_rejected(inputs, tmp_path):
    sequences, gru = inputs
    comparison = tmp_path / "alarms"
    run_experiment(sequences, gru, comparison)
    path = comparison / "calibration.json"
    value = json.loads(path.read_text())
    value["thresholds"]["gru"] += 1
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="calibration"):
        run_diagnostics(sequences, gru, comparison, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
