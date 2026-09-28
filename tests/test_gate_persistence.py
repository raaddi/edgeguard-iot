import math

from ml.gate_persistence import PersistenceMetrics, predict


def values(closed, opened, current):
    return dict(closed_contact=closed, open_contact=opened, current_a=current)


def test_reference_uses_only_last_input_and_does_not_fill_missing_values():
    history = [values(1, 0, .2), values(0, 1, None)]
    result = predict(history)
    assert result == values(0, 1, None)
    result["closed_contact"] = 1
    assert history[-1]["closed_contact"] == 0


def test_metrics_keep_units_denominators_and_missing_targets_separate():
    metrics = PersistenceMetrics()
    assert metrics.report()["channels"]["current_a"]["mae_a"] is None
    metrics.add(values(1, 0, .2), values(0, 1, .4))
    metrics.add(values(0, 1, .4), values(0, 1, .4))
    metrics.add(values(0, 1, None), values(0, 1, .3))
    metrics.add(values(0, 1, .3), values(0, 1, None))
    report = metrics.report()
    assert report["examples"] == 4
    current = report["channels"]["current_a"]
    assert current["pairs"] == 2 and current["missing_target"] == current["missing_prediction"] == 1
    assert math.isclose(current["mae_a"], .1)
    assert math.isclose(current["rmse_a"], math.sqrt(.02))
    contact = report["channels"]["closed_contact"]
    assert contact["errors"] == contact["target_changes"] == 1
    assert contact["error_rate"] == .25 and contact["unchanged_pairs"] == 3
