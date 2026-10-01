import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("torch")

from ml.gate_alarm_experiment import METHODS, run_experiment
from ml.gate_forecast_data import SequenceDataset
from ml.gate_gru_experiment import run_experiment as train_gru
from ml.gate_residuals import ResidualScaler
from ml.gate_sequence_export import export_sequences
from ml.gate_split import load_sessions, split_sessions
from simulator.gate_pilot import run_suite


@pytest.fixture
def inputs(tmp_path):
    suite = run_suite(output=tmp_path, suite_id="pilot")
    plan = split_sessions(load_sessions([suite]))
    split = tmp_path / "split.json"
    split.write_text(json.dumps(plan), encoding="utf-8")
    sequences, gru = tmp_path / "sequences", tmp_path / "gru"
    export_sequences(split, sequences)
    train_gru(sequences, gru, epochs=1)
    return sequences, gru


def test_comparison_freezes_before_faults_and_test_and_keeps_common_exposure(inputs, tmp_path, monkeypatch):
    sequences, gru = inputs
    output = tmp_path / "comparison"
    before = (gru / "weights.pt").read_bytes()
    original = SequenceDataset.sessions
    order = []
    def checked(self, partition, **kwargs):
        order.append((partition, kwargs.get("normal_only", False)))
        if not kwargs.get("normal_only", False):
            assert (output / "calibration.json").exists()
            assert (output / "baselines.joblib").exists()
        yield from original(self, partition, **kwargs)
    monkeypatch.setattr(SequenceDataset, "sessions", checked)
    result = run_experiment(sequences, gru, output)
    assert order == [("train", True), ("validation", True), ("validation", False), ("test", False)]
    assert before == (gru / "weights.pt").read_bytes() == (output / "gru" / "weights.pt").read_bytes()
    assert result["calibration"]["training_forecasts"] == 141
    assert result["calibration"]["baseline_training_rows"] == 161
    assert result["calibration"]["normal_validation_samples"] == 141
    for partition in ("validation", "test"):
        assert set(result["partitions"][partition]) == set(METHODS)
        totals = [result["partitions"][partition][m]["overall"] for m in METHODS]
        assert len({r["events"] for r in totals}) == 1
        assert all(r["normal_duration_ms"] == 7000 for r in totals)
    assert all(result["partitions"]["validation"][m]["overall"]["normal_alarms"] == 0 for m in METHODS)
    for path in (output / "predictions" / "test").glob("*.json"):
        prediction = json.loads(path.read_text())
        assert prediction["logical_ms"] == list(range(1000, 8001, 50))
        assert "labels" not in prediction
        assert all(len(v) == 141 for v in prediction["alarms"].values())
        assert (output / "labels" / "test" / path.name).exists()
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["report_sha256"] == hashlib.sha256((output / "report.json").read_bytes()).hexdigest()
    saved = json.loads((output / "calibration.json").read_text())
    for method in ("gru", "persistence"):
        scaler = ResidualScaler(tuple(saved["scales"][method]))
        assert scaler.scores(np.array([[1., 0., .1]]), np.array([[1., 0., .1]])) == [0.]
    with pytest.raises(FileExistsError):
        run_experiment(sequences, gru, output)


def test_foreign_sequence_export_is_rejected_before_output(inputs, tmp_path):
    sequences, gru = inputs
    manifest = sequences / "manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    output = tmp_path / "wrong-source"
    with pytest.raises(ValueError, match="identical"):
        run_experiment(sequences, gru, output)
    assert not output.exists()


def test_changed_raw_test_fails_after_calibration(inputs, tmp_path):
    sequences, gru = inputs
    dataset = SequenceDataset(sequences)
    session = dataset.plan["partitions"]["test"][0]
    raw = Path(session["path"]) / "observations.jsonl"
    raw.write_bytes(raw.read_bytes() + b"\n")
    output = tmp_path / "bad-raw"
    with pytest.raises(ValueError, match="Raw pilot hash"):
        run_experiment(sequences, gru, output)
    assert (output / "calibration.json").exists()
    assert json.loads((output / "manifest.json").read_text())["status"] == "failed"
    assert not (output / "report.json").exists()
