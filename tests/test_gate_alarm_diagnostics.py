import pytest

from ml.gate_alarm_diagnostics import diagnose_events


def diagnostic(scores, labels):
    return diagnose_events(list(range(0, len(scores) * 50, 50)), scores, labels, 1)


def test_threshold_equality_and_short_spike_are_distinct():
    rows = diagnostic([1, 1, 0, 2, 2, 0], [True, True, False, True, True, False])
    assert [r["reason"] for r in rows] == [
        "below_threshold", "insufficient_persistence_within_event"]
    assert rows[1]["detected_by_persistence"] == {"1": True, "3": False, "5": False}


def test_event_boundary_does_not_reset_alarm_or_backdate_start():
    rows = diagnostic([2] * 7, [False, False, False, True, True, True, True])
    assert rows[0]["reason"] == "alarm_started_before_event"
    assert rows[0]["detected_by_persistence"] == {"1": False, "3": False, "5": True}
    rows = diagnostic([2] * 5, [False, False, True, True, True])
    assert rows[0]["reason"] == "detected"
    assert rows[0]["alarm_start_ms"] == 100


def test_alarm_after_event_is_not_a_detection():
    row = diagnostic([0, 2, 2, 2], [False, True, True, False])[0]
    assert row["reason"] == "insufficient_persistence_within_event"
    assert row["alarm_start_ms"] is None


@pytest.mark.parametrize("times,scores,labels", [
    ([0, 100], [2, 2], [True, True]),
    ([0, 50], [2, None], [True, True]),
    ([0, 50], [2, float('nan')], [True, True]),
    ([0, 50], [2, 2], [True]),
])
def test_incomplete_inputs_are_rejected(times, scores, labels):
    with pytest.raises(ValueError):
        diagnose_events(times, scores, labels, 1)
