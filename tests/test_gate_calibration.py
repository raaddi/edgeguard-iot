import pytest

from ml.gate_calibration import calibrate_sessions
from ml.gate_evaluation import alarms


def test_isolated_spike_does_not_set_sustained_threshold():
    sessions = [[1, 1, 20, 1, 1], [2, 3, 4, 2]]
    thresholds = calibrate_sessions(sessions)
    assert thresholds == {"sample_max": 20, "sustained_max": 2}
    for threshold in thresholds.values():
        assert not any(any(alarms(s, threshold)) for s in sessions)
    assert alarms([3, 3, 3], thresholds["sustained_max"]) == [False, False, True]


def test_triples_do_not_cross_session_boundaries():
    assert calibrate_sessions([[0, 0, 9, 9], [9, 0, 0]])["sustained_max"] == 0


@pytest.mark.parametrize("sessions", [[], [[1, 2]], [[1, None, 2]], [[1, float('nan'), 2]]])
def test_invalid_calibration_is_rejected(sessions):
    with pytest.raises(ValueError):
        calibrate_sessions(sessions)
