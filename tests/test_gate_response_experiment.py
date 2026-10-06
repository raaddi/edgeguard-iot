import json

import numpy as np
import pytest

pytest.importorskip("torch")

from ml import gate_response_experiment as experiment
from ml import gate_response_export as exporter
from ml.gate_response_data import ResponseDataset


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(exporter, "ROLE_SEEDS", {
        "train": (3000,), "selection": (4000,),
        "calibration": (5000,), "evaluation": (6000,),
    })
    monkeypatch.setattr(experiment, "TRAINING_SEEDS", (7,))
    root = tmp_path / "responses"
    exporter.export_responses(root)
    return root


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_runner_freezes_all_models_before_later_roles_and_reports_idle(source, tmp_path, monkeypatch):
    output = tmp_path / "study"
    original = ResponseDataset.sessions
    accesses = []
    def checked(self, role):
        accesses.append(role)
        if role in ("calibration", "evaluation"):
            assert (output / "frozen.json").is_file()
            assert (output / "baseline.json").is_file()
            assert (output / "models/response-7/weights.pt").is_file()
            assert (output / "models/sensor-7/weights.pt").is_file()
        yield from original(self, role)
    monkeypatch.setattr(ResponseDataset, "sessions", checked)
    report = experiment.run_experiment(source, output, epochs=1)
    assert accesses == ["train", "selection", "selection", "calibration", "evaluation"]
    manifest = read(output / "manifest.json")
    assert manifest["status"] == "completed" and manifest["training_seeds"] == [7]
    assert len(manifest["models"]) == 2 and len(manifest["prediction_files"]) == 26
    assert manifest["report_sha256"] == experiment.digest(output / "report.json")
    assert manifest["frozen_sha256"] == experiment.digest(output / "frozen.json")
    for entry in manifest["prediction_files"]:
        assert experiment.digest(output / entry["response_file"]) == entry["response_sha256"]
        assert experiment.digest(output / entry["sensor_file"]) == entry["sensor_sha256"]
    training = report["training"]["7"]
    assert training["response"]["training_examples"] == 10
    assert training["response"]["selection_examples"] == 10
    assert training["sensor"]["training_examples"] == training["sensor"]["selection_examples"] == 1743
    normal = report["roles"]["evaluation"]["by_case"]["normal"]
    assert normal["response_examples"] == 23 and normal["sensor_examples"] == 2905
    assert set(normal["response"]) == {"median", "gru_7"}
    assert set(normal["sensor"]) == {"persistence", "gru_7"}
    conditions = report["roles"]["evaluation"]["normal_by_condition"]
    assert set(conditions) == {"cycles", "repeats", "idle", "slow", "reversals"}
    idle = conditions["idle"]
    assert idle["response_examples"] == 0 and idle["sensor_examples"] == 581
    assert idle["response"]["median"]["contact"]["mae_ms"] is None
    assert idle["response_seed_spread"]["ack"]["minimum_mae_ms"] is None
    assert normal["response"]["gru_7"]["contact"]["censored"] == 2
    assert (output / "protocol.md").read_bytes() == experiment.PROTOCOL_PATH.read_bytes()
    before = (output / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        experiment.run_experiment(source, output, epochs=1)
    assert (output / "manifest.json").read_bytes() == before


def test_corrupted_late_role_fails_after_freezing_and_preserves_failed_manifest(source, tmp_path):
    output = tmp_path / "failed"
    entry = next(e for e in read(source / "manifest.json")["sessions"] if e["role"] == "evaluation")
    (source / entry["examples_file"]).write_text("corrupted", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        experiment.run_experiment(source, output, epochs=1)
    assert (output / "frozen.json").is_file()
    assert read(output / "manifest.json")["status"] == "failed"
    assert not (output / "report.json").exists()


def test_metrics_preserve_censor_counts_and_never_use_follow_up_as_target():
    target = np.array([[100., 200.], [300., np.nan]])
    predicted = np.array([[200., 100.], [100., 9999.]])
    examples = [{"y": {"ack": {"observed": True, "censor_reason": None},
                       "contact": {"observed": True, "censor_reason": None}}},
                {"y": {"ack": {"observed": True, "censor_reason": None},
                       "contact": {"observed": False, "censor_reason": "superseded"}}}]
    report = experiment.response_metrics(target, predicted, examples)
    assert report["ack"]["mae_ms"] == 150 and report["ack"]["bias_ms"] == -50
    assert report["contact"]["observed"] == report["contact"]["censored"] == 1
    assert report["contact"]["censor_reasons"] == {"superseded": 1}
    assert report["contact"]["mae_ms"] == 100 and report["contact"]["bias_ms"] == -100
    with pytest.raises(ValueError, match="nonnegative"):
        experiment.response_metrics(target, np.full_like(target, -1), examples)


@pytest.mark.parametrize("epochs", [0, True, 1.5, 201])
def test_invalid_epochs_do_not_create_output(tmp_path, epochs):
    output = tmp_path / "invalid"
    with pytest.raises(ValueError, match="epochs"):
        experiment.run_experiment(tmp_path / "missing", output, epochs=epochs)
    assert not output.exists()
