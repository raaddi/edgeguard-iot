from dataclasses import asdict

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ml.gate_forecast_data import FEATURE_NAMES, ForecastPreprocessor
from ml.gate_gru import fit_gru, forecast, load_forecaster, loss, save_forecaster


def tiny_normal_data():
    # Small artificial fixture for optimization/serialization, not research evidence.
    x = np.zeros((32, 4, 20), dtype=np.float32)
    x[16:, :, FEATURE_NAMES.index("closed_contact")] = 1
    y = np.zeros((32, 3), dtype=np.float32)
    y[16:, 0] = 1
    y[:, 2] = np.nan
    return x, y


def test_missing_current_has_no_loss_or_gradient_and_contacts_still_learn():
    output = torch.tensor([[0., 0., 123.]], requires_grad=True)
    target = torch.tensor([[1., 0., 0.]])
    mask = torch.tensor([[True, True, False]])
    value = loss(output, target, mask)
    value.backward()
    assert torch.isfinite(value) and output.grad[0, 2] == 0
    assert output.grad[0, 0] != 0 and output.grad[0, 1] != 0


def test_seeded_training_learns_roundtrips_and_preserves_preprocessing(tmp_path):
    x, y = tiny_normal_data()
    prep = ForecastPreprocessor.fit(x, y)
    before = asdict(prep)
    model, history = fit_gru(prep, x, y, x, y, epochs=8, seed=7)
    predicted = forecast(model, prep, x)
    assert history["best_validation_loss"] < history["initial_validation_loss"]
    assert history["best_epoch"] == min(history["history"], key=lambda r: r["normal_validation_loss"])["epoch"]
    assert asdict(prep) == before and np.isnan(predicted[:, 2]).all()
    repeated, second = fit_gru(prep, x, y, x, y, epochs=8, seed=7)
    assert history == second
    np.testing.assert_array_equal(predicted, forecast(repeated, prep, x))
    save_forecaster(tmp_path, model, prep, {"history_samples": 4, "horizon_samples": 1})
    restored, restored_prep, config = load_forecaster(tmp_path)
    np.testing.assert_array_equal(predicted, forecast(restored, restored_prep, x))
    assert config["sequence_config"]["history_samples"] == 4
    with pytest.raises(ValueError, match="history shape"):
        forecast(restored, restored_prep, x[:, :2])
    weights = tmp_path / "weights.pt"
    weights.write_bytes(weights.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="hash"):
        load_forecaster(tmp_path)


@pytest.mark.parametrize("epochs,seed", [(0, 42), (True, 42), (201, 42), (1, -1)])
def test_invalid_fit_config(epochs, seed):
    x, y = tiny_normal_data()
    with pytest.raises(ValueError):
        fit_gru(ForecastPreprocessor.fit(x, y), x, y, x, y, epochs=epochs, seed=seed)
