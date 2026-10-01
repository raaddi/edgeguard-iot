from dataclasses import asdict

import numpy as np
import pytest

from ml.gate_evaluation import evaluate
from ml.gate_residuals import ResidualScaler, common_labels, timed_alarms


def test_scaling_is_frozen_and_current_units_do_not_change_relative_score():
    actual = np.array([[1, 0, .2], [0, 1, .4]])
    predicted = np.array([[.8, .1, .1], [.1, .7, .2]])
    scaler = ResidualScaler.fit(actual, predicted)
    state = asdict(scaler)
    future = actual.copy()
    future[:, 2] *= 10
    scores = scaler.scores(future, predicted)
    assert asdict(scaler) == state
    conversion = np.array([1, 1, 1000])
    other = ResidualScaler.fit(actual * conversion, predicted * conversion)
    np.testing.assert_allclose(scores, other.scores(future * conversion, predicted * conversion))
    assert scaler.scores(actual, actual) == [0, 0]


def test_perfect_training_has_finite_floor_and_missing_measurement_is_not_zero():
    actual = np.array([[1., 0., .2]])
    scaler = ResidualScaler.fit(actual, actual)
    assert scaler.scales == (1e-6, 1e-6, 1e-6)
    for bad in (np.nan, np.inf):
        missing = actual.copy()
        missing[0, 2] = bad
        with pytest.raises(ValueError, match="complete finite"):
            scaler.scores(missing, actual)


def test_alarm_is_not_backdated_and_gaps_missing_values_and_equality_reset_it():
    assert timed_alarms([0, 50, 100, 150], [2, 2, 2, 1], 1) == [False, False, True, False]
    assert timed_alarms([0, 50, 150, 200, 250], [2] * 5, 1) == [False, False, False, False, True]
    assert timed_alarms([0, 50, 100, 150], [2, None, 2, 2], 1) == [False] * 4
    with pytest.raises(ValueError):
        timed_alarms([0, 50], [2, np.nan], 1)


def test_common_support_keeps_event_onset_and_excludes_warmup_from_exposure():
    times = list(range(1000, 1350, 50))
    full = [False] * 22 + [True] * 4 + [False]
    labels = common_labels(full, times)
    flags = timed_alarms(times, [0, 0, 2, 2, 2, 2, 0], 1)
    result = evaluate([dict(labels=labels, alarms=flags, normal=False)])
    assert result["detected_events"] == 1 and result["detection_delays_ms"] == [100]
    normal = evaluate([dict(labels=[False] * len(times), alarms=flags, normal=True)])
    assert normal["normal_duration_ms"] == 300
    full[19] = True
    with pytest.raises(ValueError, match="Warmup"):
        common_labels(full, times)


@pytest.mark.parametrize("times", [[1000, 1100, 1150], [1050, 1000], [1001, 1051]])
def test_incomplete_or_unordered_common_grid_rejected(times):
    with pytest.raises(ValueError):
        common_labels([False] * 24, times)
