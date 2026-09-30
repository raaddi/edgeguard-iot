import json

import pytest

pytest.importorskip("torch")

from ml.gate_forecast_data import SequenceDataset
from ml.gate_gru_experiment import run_experiment
from ml.gate_sequence_export import export_sequences
from ml.gate_split import load_sessions, split_sessions
from simulator.gate_pilot import run_suite


@pytest.fixture
def sequences(tmp_path):
    suite = run_suite(output=tmp_path, suite_id="pilot")
    plan = split_sessions(load_sessions([suite]))
    split = tmp_path / "split.json"
    split.write_text(json.dumps(plan), encoding="utf-8")
    root = tmp_path / "sequences"
    export_sequences(split, root)
    return root


def test_runner_freezes_model_before_test_and_reports_both_methods(sequences, tmp_path, monkeypatch):
    output = tmp_path / "gru"
    original = SequenceDataset.sessions
    accesses = []
    def checked(self, partition, **kwargs):
        accesses.append((partition, kwargs.get("normal_only", False)))
        if partition == "test" or (partition == "validation" and not kwargs.get("normal_only")):
            assert (output / "weights.pt").is_file() and (output / "model.json").is_file()
        yield from original(self, partition, **kwargs)
    monkeypatch.setattr(SequenceDataset, "sessions", checked)
    result = run_experiment(sequences, output, epochs=2)
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert accesses[:2] == [("train", True), ("validation", True)]
    normal = result["partitions"]["test"]["by_case"]["normal"]
    assert set(normal) == {"gru", "persistence"}
    assert normal["gru"]["current_a"]["pairs"] == normal["persistence"]["current_a"]["pairs"] == 141
    assert result["training"]["training_examples"] == 141
    assert len(list((output / "predictions" / "test").glob("*.jsonl"))) == 4
    with pytest.raises(FileExistsError):
        run_experiment(sequences, output, epochs=2)


def test_corrupt_test_fails_after_training_without_completed_report(sequences, tmp_path):
    output = tmp_path / "failed"
    next((sequences / "test").glob("*.jsonl")).write_text("corrupted", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        run_experiment(sequences, output, epochs=1)
    assert (output / "weights.pt").exists()
    assert json.loads((output / "manifest.json").read_text())["status"] == "failed"
    assert not (output / "report.json").exists()
