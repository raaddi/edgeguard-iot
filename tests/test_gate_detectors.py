import joblib
import numpy as np
import pytest

from ml.gate_detectors import GateDetectors, calibrate
from ml.gate_features import extract_features
from simulator.gate_pilot import simulate_session


@pytest.fixture(scope="module")
def fitted():
    obs, events, _ = simulate_session(seed=42, case="normal", run_id="train")
    rows = [r["x"] for r in extract_features(obs, events)]
    return GateDetectors.fit(rows), rows


def test_scoring_does_not_fit_preprocessing_or_change_model(fitted):
    model, rows = fitted
    statistics = model.imputer.statistics_.copy()
    before = model.scores(rows)
    different = [dict(row, current_a=99.0) for row in rows]
    assert all(np.isfinite(model.scores(different)["isolation_forest"]))
    np.testing.assert_array_equal(statistics, model.imputer.statistics_)
    assert before == model.scores(rows)
    assert model.rule_limits["current_a"] == max(r["current_a"] for r in rows)


def test_saved_model_preserves_scores_and_schema(fitted, tmp_path):
    model, rows = fitted
    path = tmp_path / "own-model.joblib"
    joblib.dump(model, path)
    loaded = joblib.load(path)  # Only a model produced by this test is loaded.
    assert loaded.feature_names == model.feature_names
    assert loaded.scores(rows) == model.scores(rows)
    with pytest.raises(ValueError, match="schema"):
        loaded.scores([dict(rows[0], case="normal")])


def test_calibration_uses_only_supplied_normal_validation_scores():
    assert calibrate([0.2, 0.4, 0.3]) == 0.4
    with pytest.raises(ValueError):
        calibrate([])
