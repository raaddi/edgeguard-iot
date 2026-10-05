from copy import deepcopy

import pytest

from ml.gate_response_targets import extract_response_examples
from simulator.gate_pilot import simulate_session
from simulator.gate_session import GateSessionSettings


def session(case="normal", schedule=((1000, 110), (5000, 0))):
    settings = GateSessionSettings(schedule=schedule, stroke_bounds_ms=(1000, 1000), nominal_delays_ms=(100,))
    return simulate_session(seed=42, case=case, run_id="response-test", settings=settings)[:2]


def examples(*args, **kwargs):
    return extract_response_examples(*args, **kwargs)["examples"]


def test_send_time_is_input_endpoint_and_ack_is_distinct_from_physical_completion():
    rows = examples(*session())
    assert len(rows) == 2
    first = rows[0]
    assert first["input_times_ms"] == list(range(50, 1001, 50))
    assert first["x"][-1]["last_command_degrees"] == 110
    assert first["x"][-1]["pending_commands"] == 1
    assert first["x"][-1]["last_result_delay_ms"] is None
    assert first["y"]["ack"] == {"observed": True, "duration_ms": 100, "follow_up_ms": 100,
                                   "censor_reason": None, "accepted": True}
    assert first["y"]["contact"]["duration_ms"] == 1100
    assert all(not {"seed", "case", "run_id", "command_id", "target_duration_ms"} & x.keys() for r in rows for x in r["x"])


def test_future_ack_and_sensor_changes_never_change_earlier_inputs():
    normal = examples(*session())[0]
    delayed = examples(*session(case="command_delay"))[0]
    assert normal["x"] == delayed["x"]
    assert delayed["y"]["ack"]["duration_ms"] == 1200
    obs, events = session()
    obs = deepcopy(obs)
    obs[30]["open_contact"] = True
    obs[30]["current_a"] = 99.0
    altered = examples(obs, events)[0]
    assert altered["x"] == normal["x"]
    assert altered["y"]["contact"]["duration_ms"] == 500


def test_prefix_preserves_inputs_and_completed_targets_but_can_end_censoring():
    obs, events = session()
    full = examples(obs, events)[0]
    def prefix(now):
        return examples([o for o in obs if o["logical_ms"] <= now],
                        [e for e in events if e["logical_ms"] <= now])[0]
    early = prefix(1050)
    assert early["x"] == full["x"]
    assert early["y"]["ack"]["duration_ms"] is None
    assert early["y"]["ack"]["follow_up_ms"] == 50
    assert early["y"]["contact"]["censor_reason"] == "no_result"
    assert prefix(2200) == full


def test_already_achieved_target_is_confirmed_after_ack_not_before_command():
    row = examples(*session(schedule=((1000, 0),)))[0]
    assert row["y"]["contact"]["duration_ms"] == row["y"]["ack"]["duration_ms"] == 100


def test_same_target_repeat_shares_confirmation_without_canceling_first_command():
    first, second = examples(*session(schedule=((1000, 110), (1500, 110))))
    assert first["y"]["contact"]["duration_ms"] == 1100
    assert second["y"]["contact"]["duration_ms"] == 600
    assert first["prediction_ms"] + 1100 == second["prediction_ms"] + 600
    before = deepcopy(second)
    first["x"][-1]["current_a"] = 99
    assert second == before


def test_reversal_cancels_on_acceptance_and_same_tick_sample_cannot_confirm_old_target():
    obs, events = session(schedule=((1000, 110), (1400, 0)))
    obs[30]["open_contact"] = True  # 1500 ms: opposite target already accepted.
    first, second = examples(obs, events)
    assert first["y"]["contact"] == {"observed": False, "duration_ms": None,
        "follow_up_ms": 500, "censor_reason": "superseded"}
    assert second["y"]["contact"]["observed"]


def test_sensor_gap_censors_contact_but_not_independently_logged_ack():
    obs, events = session(case="command_delay")
    obs = [o for o in obs if o["logical_ms"] != 1500]
    first = examples(obs, events)[0]
    assert first["y"]["ack"]["duration_ms"] == 1200
    assert first["y"]["contact"]["censor_reason"] == "sample_gap"
    assert first["y"]["contact"]["follow_up_ms"] == 500
    assert first["y"]["contact"]["duration_ms"] is None


def test_unfinished_motion_and_rejected_command_are_not_zero_duration_targets():
    row = examples(*session(case="motion_stall", schedule=((1000, 110),)))[0]
    assert row["y"]["contact"] == {"observed": False, "duration_ms": None,
        "follow_up_ms": 7000, "censor_reason": "end_of_session"}
    obs, events = session()
    events[1]["message"].update(status="rejected", reason="internal_error")
    row = examples(obs, events)[0]
    assert row["y"]["ack"]["observed"] and not row["y"]["ack"]["accepted"]
    assert row["y"]["contact"]["censor_reason"] == "rejected"
    assert row["y"]["contact"]["duration_ms"] is None


def test_last_sample_confirmation_is_observed():
    obs, events = session(case="open_contact_stuck_low", schedule=((1000, 110),))
    obs[-1]["open_contact"] = True
    row = examples(obs, events)[0]
    assert row["y"]["contact"]["observed"]
    assert row["y"]["contact"]["duration_ms"] == 7000


def test_input_exclusions_are_audited_and_state_resets_between_sessions():
    obs, events = session()
    result = extract_response_examples(obs, events, history_samples=200)
    assert not result["examples"]
    assert [r["reason"] for r in result["excluded"]] == ["missing_history"] * 2
    gapped = [o for o in obs if o["logical_ms"] != 750]
    result = extract_response_examples(gapped, events)
    assert result["excluded"][0]["reason"] == "gap_in_history"
    assert len(result["examples"]) == 1
    idle, no_events = session(schedule=())
    assert examples(idle, no_events) == []
    assert examples(*session())[0]["x"][-1]["last_result_delay_ms"] is None


def test_ambiguous_send_times_and_already_available_results_are_not_used_as_forecasts():
    obs, events = session()
    events[1]["logical_ms"] = 1000
    events[1]["message"]["handled_uptime_ms"] = 1000
    result = extract_response_examples(obs, events)
    assert result["excluded"][0]["reason"] == "instant_result"
    obs, events = session()
    events[2]["logical_ms"] = events[2]["message"]["observed_uptime_ms"] = 1000
    events.sort(key=lambda e: e["logical_ms"])
    with pytest.raises(ValueError, match="distinct command"):
        extract_response_examples(obs, events)


@pytest.mark.parametrize("value", [0, True, 1.5, 201])
def test_invalid_history_size_is_rejected(value):
    with pytest.raises(ValueError, match="history_samples"):
        extract_response_examples(*session(), history_samples=value)


def test_events_after_last_sample_require_a_separately_defined_channel_end_contract():
    obs, events = session(case="command_delay")
    with pytest.raises(ValueError, match="beyond the observed session"):
        extract_response_examples([o for o in obs if o["logical_ms"] <= 6000], events)
