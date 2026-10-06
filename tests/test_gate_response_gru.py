"""Censor-aware optimization and persistence checks; fixtures are not results."""

from dataclasses import asdict
import hashlib
import json

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from ml.gate_forecast_data import FEATURE_NAMES, ForecastPreprocessor
from ml.gate_response_gru import (MedianResponseBaseline, ResponseGRU, fit_response_gru,
                                  forecast_response, load_response_forecaster, response_loss,
                                  save_response_forecaster, selection_loss)


def tiny_data():
    x = np.zeros((32, 4, len(FEATURE_NAMES)), dtype=np.float32)
    x[:16, :, FEATURE_NAMES.index("closed_contact")] = 1
    x[16:, :, FEATURE_NAMES.index("last_command_degrees")] = 110
    y = np.tile([100., 500.], (32, 1)).astype(np.float32)
    y[16:] = [200., 1000.]
    y[:2, 1] = np.nan
    sensor_y = np.zeros((32, 3), dtype=np.float32)
    sensor_y[:, 2] = np.nan
    return x, y, ForecastPreprocessor.fit(x, sensor_y)


def test_masked_log_loss_balances_channels_and_ignores_nan_gradients():
    output = torch.tensor([[1., 2.], [3., 4.]], requires_grad=True)
    targets = torch.tensor([[2., float("nan")], [float("nan"), 8.]])
    mask = torch.isfinite(targets)
    value = response_loss(output, targets, mask)
    assert value.item() == 8.5
    value.backward()
    torch.testing.assert_close(output.grad, torch.tensor([[-1., 0.], [0., -4.]]))
    empty = torch.tensor([[100., 999.]], requires_grad=True)
    value = response_loss(empty, torch.full_like(empty, float("nan")), torch.zeros_like(empty, dtype=torch.bool))
    value.backward()
    assert value.item() == 0 and not empty.grad.any()
    only_ack = torch.tensor([[1., 2.]], requires_grad=True)
    assert response_loss(only_ack, torch.tensor([[3., float("nan")]]),
                         torch.tensor([[True, False]])).item() == 4


def test_selection_loss_counts_each_observed_duration_across_batches():
    class PassThrough(torch.nn.Module):
        def forward(self, x):
            return x

    x = torch.zeros((129, 2))
    y = torch.zeros((129, 2))
    y[128] = torch.tensor([2., 3.])
    mask = torch.ones_like(y, dtype=torch.bool)
    mask[:128, 1] = False
    y[:128, 1] = float("nan")
    assert selection_loss(PassThrough(), (x, y, mask)) == pytest.approx((4 / 129 + 9) / 2)


def test_seeded_training_roundtrip_and_fixed_architecture(tmp_path, monkeypatch):
    x, y, prep = tiny_data()
    original_prep = asdict(prep)
    model, trained = fit_response_gru(prep, x, y, x, y, epochs=8, seed=7)
    predictions = forecast_response(model, prep, x)
    assert predictions.shape == (len(x), 2) and np.isfinite(predictions).all() and (predictions >= 0).all()
    assert model.gru.input_size == 40 and model.gru.hidden_size == 16
    assert model.gru.num_layers == 1 and not model.gru.bidirectional
    assert trained["best_selection_loss"] < trained["initial_selection_loss"]
    assert trained["best_epoch"] == min(trained["history"], key=lambda row: row["normal_selection_loss"])["epoch"]
    assert asdict(prep) == original_prep
    repeated, repeated_history = fit_response_gru(prep, x, y, x, y, epochs=8, seed=7)
    assert repeated_history == trained
    np.testing.assert_array_equal(predictions, forecast_response(repeated, prep, x))
    save_response_forecaster(tmp_path, model, prep)
    original_load = torch.load
    calls = []

    def record_load(*args, **kwargs):
        calls.append(kwargs)
        return original_load(*args, **kwargs)

    monkeypatch.setattr(torch, "load", record_load)
    restored, restored_prep, config = load_response_forecaster(tmp_path)
    np.testing.assert_array_equal(predictions, forecast_response(restored, restored_prep, x))
    assert asdict(restored_prep) == original_prep
    assert config["history_samples"] == 4 and config["target_names"] == ["ack", "contact"]
    assert config["target_transform"] == "log1p(duration_ms/50)"
    assert calls == [{"map_location": "cpu", "weights_only": True}]
    with pytest.raises(ValueError, match="history shape"):
        forecast_response(restored, restored_prep, x[:, :2])
    weights = tmp_path / "weights.pt"
    weights.write_bytes(weights.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="hash"):
        load_response_forecaster(tmp_path)


@pytest.mark.parametrize("epochs,seed", [(0, 42), (True, 42), (201, 42), (1.5, 42),
                                          (1, -1), (1, True), (1, 2**32)])
def test_invalid_fit_settings(epochs, seed):
    x, y, prep = tiny_data()
    with pytest.raises(ValueError):
        fit_response_gru(prep, x, y, x, y, epochs=epochs, seed=seed)


@pytest.mark.parametrize("problem", ["shape", "history", "features", "infinity", "negative_target",
                                     "infinite_target", "no_train_ack", "no_selection_contact", "empty"])
def test_invalid_arrays(problem):
    x, y, prep = tiny_data()
    train_x, train_y, select_x, select_y = x.copy(), y.copy(), x.copy(), y.copy()
    if problem == "shape":
        train_y = y[:, :1]
    elif problem == "history":
        select_x = x[:, :2]
    elif problem == "features":
        train_x = x[:, :, :19]
    elif problem == "infinity":
        train_x[0, 0, 0] = np.inf
    elif problem == "negative_target":
        train_y[0, 0] = -1
    elif problem == "infinite_target":
        train_y[0, 0] = np.inf
    elif problem == "no_train_ack":
        train_y[:, 0] = np.nan
    elif problem == "no_selection_contact":
        select_y[:, 1] = np.nan
    elif problem == "empty":
        train_x, train_y = x[:0], y[:0]
    with pytest.raises(ValueError):
        fit_response_gru(prep, train_x, train_y, select_x, select_y, epochs=1)


def test_missing_inputs_can_be_imputed_but_nonfinite_predictions_are_rejected():
    x, y, prep = tiny_data()
    x[0, :, FEATURE_NAMES.index("current_a")] = np.nan
    model, _ = fit_response_gru(prep, x, y, x, y, epochs=1)
    assert np.isfinite(forecast_response(model, prep, x)).all()
    with torch.no_grad():
        model.output.bias.fill_(10000.)
    with pytest.raises(ValueError, match="forecasts"):
        forecast_response(model, prep, x)


@pytest.mark.parametrize("field,value", [("model_version", "wrong"), ("target_names", ["contact", "ack"]),
                                         ("hidden_size", 32), ("layers", True), ("history_samples", True),
                                         ("history_samples", 0), ("history_samples", 201),
                                         ("target_transform", "identity"), ("bidirectional", 0),
                                         ("feature_names", []), ("weights_sha256", "wrong")])
def test_invalid_saved_configuration(tmp_path, field, value):
    x, y, prep = tiny_data()
    model = ResponseGRU()
    model.history_samples = 4
    save_response_forecaster(tmp_path, model, prep)
    path = tmp_path / "model.json"
    config = json.loads(path.read_text())
    config[field] = value
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        load_response_forecaster(tmp_path)


@pytest.mark.parametrize("parameter,value", [("scale", 0.), ("scale", -1.), ("mean", float("inf")),
                                             ("median", float("nan")), ("current_scale", 0.),
                                             ("current_enabled", 1)])
def test_invalid_preprocessor_configuration(tmp_path, parameter, value):
    _, _, prep = tiny_data()
    model = ResponseGRU()
    model.history_samples = 4
    save_response_forecaster(tmp_path, model, prep)
    path = tmp_path / "model.json"
    config = json.loads(path.read_text())
    if parameter in ("scale", "mean", "median"):
        config["preprocessor"][parameter][0] = value
    else:
        config["preprocessor"][parameter] = value
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="preprocessor"):
        load_response_forecaster(tmp_path)


@pytest.mark.parametrize("state_problem", ["nonfinite", "wrong_shape"])
def test_invalid_weights_even_with_matching_hash(tmp_path, state_problem):
    _, _, prep = tiny_data()
    model = ResponseGRU()
    model.history_samples = 4
    save_response_forecaster(tmp_path, model, prep)
    state = model.state_dict()
    if state_problem == "nonfinite":
        state["output.bias"][0] = float("nan")
    else:
        state["output.bias"] = torch.zeros(3)
    weights = tmp_path / "weights.pt"
    torch.save(state, weights)
    path = tmp_path / "model.json"
    config = json.loads(path.read_text())
    config["weights_sha256"] = hashlib.sha256(weights.read_bytes()).hexdigest()
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="weights"):
        load_response_forecaster(tmp_path)


def baseline_fixture():
    x = np.zeros((5, 4, len(FEATURE_NAMES)), dtype=np.float32)
    x[0, -1, FEATURE_NAMES.index("closed_contact")] = 1
    x[2:, -1, FEATURE_NAMES.index("last_command_degrees")] = 110
    x[4, -1, FEATURE_NAMES.index("open_contact")] = 1
    y = np.asarray([[100, 100], [200, 1000], [300, 1500], [500, np.nan], [np.nan, 50]])
    return x, y


def test_median_baseline_masks_censoring_and_uses_channelwise_fallbacks():
    x, y = baseline_fixture()
    baseline = MedianResponseBaseline.fit(x, y)
    predicted = baseline.predict(x)
    np.testing.assert_array_equal(predicted, [[100, 100], [200, 1000], [400, 1500], [400, 1500], [400, 50]])
    changed = x.copy()
    changed[:, :-1] = 123
    changed[:, -1, FEATURE_NAMES.index("current_a")] = np.nan
    changed[:, -1, FEATURE_NAMES.index("last_result_delay_ms")] = 9000
    np.testing.assert_array_equal(predicted, baseline.predict(changed))
    config = json.loads(json.dumps(baseline.to_config(), allow_nan=False))
    assert config["groups"]["110:1"] == [None, 50]
    restored = MedianResponseBaseline.from_config(config)
    np.testing.assert_array_equal(predicted, restored.predict(x))
    # A target absent from training uses only global training medians.
    closed_only = MedianResponseBaseline.fit(x[:2], y[:2])
    np.testing.assert_array_equal(closed_only.predict(x[2:]), np.tile([150, 550], (3, 1)))
    # A missing already-at-target group falls back to its target medians.
    unfinished_only = MedianResponseBaseline.fit(x[2:4], y[2:4])
    np.testing.assert_array_equal(unfinished_only.predict(x[4:]), [[400, 1500]])


@pytest.mark.parametrize("problem", ["negative", "missing_global", "unexpected_group", "history", "version"])
def test_invalid_baseline_config(problem):
    x, y = baseline_fixture()
    config = MedianResponseBaseline.fit(x, y).to_config()
    if problem == "negative":
        config["groups"]["0:0"][0] = -1
    elif problem == "missing_global":
        config["global_medians"][1] = None
    elif problem == "unexpected_group":
        config["groups"]["42:0"] = [1, 1]
    elif problem == "history":
        config["history_samples"] = True
    elif problem == "version":
        config["baseline_version"] = "wrong"
    with pytest.raises(ValueError):
        MedianResponseBaseline.from_config(config)


def test_baseline_rejects_unknown_command_and_contact_states():
    x, y = baseline_fixture()
    for feature in ("last_command_degrees", "closed_contact", "open_contact"):
        invalid = x.copy()
        invalid[0, -1, FEATURE_NAMES.index(feature)] = np.nan
        with pytest.raises(ValueError):
            MedianResponseBaseline.fit(invalid, y)


def test_selection_ties_keep_the_earliest_checkpoint(monkeypatch):
    import ml.gate_response_gru as response_module

    x, y, prep = tiny_data()
    monkeypatch.setattr(response_module, "selection_loss", lambda model, tensors: 1.)
    model, history = fit_response_gru(prep, x, y, x, y, epochs=3, seed=7)
    first, _ = fit_response_gru(prep, x, y, x, y, epochs=1, seed=7)
    assert history["best_epoch"] == 1
    np.testing.assert_array_equal(forecast_response(model, prep, x), forecast_response(first, prep, x))
