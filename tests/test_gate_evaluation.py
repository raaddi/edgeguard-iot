import pytest

from ml.gate_evaluation import alarms, counterfactual_labels, evaluate, intervals
from simulator.gate_pilot import simulate_session


@pytest.mark.parametrize("profile", ["standard", "repeat_open", "early_return", "idle"])
def test_labels_follow_observable_divergence_not_configured_fault(profile):
    ref = simulate_session(seed=42, case="normal", run_id="reference", profile=profile)
    assert not any(counterfactual_labels(*ref[:2], *ref[:2]))
    for case in ("command_delay", "motion_stall", "open_contact_stuck_low"):
        faulty = simulate_session(seed=42, case=case, run_id="faulty", profile=profile)
        labels = counterfactual_labels(*faulty[:2], *ref[:2])
        assert any(labels) == (profile != "idle")
        assert not any(labels[:21])  # No observable fault before the first response.


def test_misaligned_reference_is_rejected():
    ref = simulate_session(seed=42, case="normal", run_id="reference")
    with pytest.raises(ValueError, match="aligned"):
        counterfactual_labels(ref[0][1:], ref[1], *ref[:2])


def test_alarm_is_not_backdated_and_early_alarm_does_not_get_free_credit():
    assert alarms([0, 2, 2, 2, 0], 1) == [False, False, False, True, False]
    result = evaluate([{"normal": False, "labels": [False, False, True, True, False],
                        "alarms": [False, True, True, True, False]}])
    assert result["detected_events"] == 0 and result["unmatched_alarms"] == 1
    assert result["missed_events"] == 1 and result["detection_delays_ms"] == []


def test_events_match_once_with_explicit_false_alarms_and_misses():
    result = evaluate([
        {"normal": False, "labels": [False, True, True, True, True, False, True],
         "alarms": [False, False, True, False, True, False, False]},
        {"normal": True, "labels": [False] * 5, "alarms": [False, False, True, True, False]},
    ])
    assert result["events"] == 2 and result["detected_events"] == 1
    assert result["alarms"] == 3 and result["unmatched_alarms"] == 2
    assert result["event_recall"] == 0.5 and result["event_precision"] == 1 / 3
    assert result["detection_delays_ms"] == [50]
    assert result["normal_duration_ms"] == 200
    assert result["false_alarms_per_normal_hour"] == 18000
    assert intervals([True, False, True]) == [(0, 1), (2, 3)]
