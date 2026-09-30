import numpy as np

from ml.gate_forecast_metrics import forecast_metrics


def test_forecast_metrics_expose_transition_errors_and_common_coverage():
    target = np.array([[1., 0., .4], [1., 0., .2], [0., 1., .2]])
    last = np.array([[0., 0., .2], [1., 0., np.nan], [0., 1., .2]])
    predicted = np.array([[.8, .1, .3], [.8, .1, .3], [.7, .9, .3]])
    metrics = forecast_metrics(target, predicted, last)
    closed = metrics["closed_contact"]
    assert closed["pairs"] == 3 and closed["changed_pairs"] == 1
    assert closed["changed_errors"] == 0 and closed["unchanged_errors"] == 1
    assert closed["errors"] == 1
    assert np.isclose(closed["brier"], (.04 + .04 + .49) / 3)
    assert metrics["current_a"]["pairs"] == 2  # Both methods compared on available last/target.
    assert np.isclose(metrics["current_a"]["mae_a"], .1)
    absent = predicted.copy()
    absent[:, 2] = np.nan
    missing = forecast_metrics(target, absent, last)["current_a"]
    assert missing["mae_a"] is None and missing["missing_predictions_on_eligible"] == 2
