from copy import deepcopy

import pytest

from ml.gate_features import extract_features
from simulator.gate_pilot import simulate_session


def session(**kwargs):
    return simulate_session(seed=42, case="normal", run_id="features-test", **kwargs)[:2]


def at(rows, t):
    return next(row["x"] for row in rows if row["logical_ms"] == t)


def test_future_samples_and_commands_do_not_change_past_features():
    obs, events = session()
    full = extract_features(obs, events)
    prefix = extract_features([o for o in obs if o["logical_ms"] <= 1300],
                              [e for e in events if e["logical_ms"] <= 1300])
    assert prefix == [r for r in full if r["logical_ms"] <= 1300]
    obs[-1]["current_a"] = 99.0
    assert prefix == extract_features(obs, events)[:len(prefix)]
    assert all(set(row) == {"logical_ms", "x"} for row in full)
    assert not {"seed", "profile", "case", "run_id", "device_id"} & set(full[0]["x"])


def test_command_ack_and_contact_are_distinct_and_window_left_edge_is_excluded():
    rows = extract_features(*session())
    assert at(rows, 950)["last_command_degrees"] is None
    assert at(rows, 1000)["pending_commands"] == 1
    assert at(rows, 1000)["last_result_delay_ms"] is None
    assert at(rows, 1050)["last_result_delay_ms"] == 50
    assert at(rows, 1050)["pending_commands"] == 0
    assert at(rows, 1050)["target_contact_delay_ms"] is None
    assert at(rows, 2500)["target_contact_delay_ms"] > 0
    assert at(rows, 1950)["commands_in_window"] == 1
    assert at(rows, 2000)["commands_in_window"] == 0


def test_missing_current_and_sample_gaps_are_not_zero_or_imputed():
    obs, events = session(measure_current=False)
    rows = extract_features(obs, events)
    assert all(r["x"]["current_missing"] == 1 and r["x"]["current_mean_a"] is None for r in rows)
    shortened = [o for o in obs if o["logical_ms"] not in (1000, 1050)]
    x = at(extract_features(shortened, events), 1100)
    assert x["sample_gap_ms"] == 150 and x["sample_coverage"] == 0.9
    assert x["contact_transitions"] == 0  # Do not infer the missed transition.


def test_idle_and_repeated_commands_do_not_inherit_other_session_state():
    extract_features(*session())
    idle = extract_features(*session(profile="idle"))
    assert all(r["x"]["last_command_degrees"] is None for r in idle)
    repeated = extract_features(*session(profile="repeat_open"))
    assert at(repeated, 1500)["commands_in_window"] == 2
    assert at(repeated, 1500)["command_age_ms"] == 0


def test_rejected_command_does_not_change_accepted_target():
    obs, events = session()
    events[-1]["message"].update(status="rejected", reason="internal_error")
    x = at(extract_features(obs, events), 6000)
    assert x["last_command_degrees"] == 0 and x["accepted_target_degrees"] == 110
    assert x["pending_commands"] == 0 and x["last_result_accepted"] == 0


def test_distinct_feedback_node_is_supported_but_shared_node_boot_must_match():
    extract_features(*session(feedback_device_id="feedback_02"))
    obs, events = session()
    for o in obs:
        o["boot_id"] = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(ValueError, match="boot"):
        extract_features(obs, events)


@pytest.mark.parametrize("bad", ["label", "nan", "bool_current", "mixed", "order", "seq", "orphan"])
def test_invalid_inputs_are_rejected(bad):
    obs, events = deepcopy(session())
    if bad == "label": obs[0]["case"] = "normal"
    if bad == "nan": obs[0]["current_a"] = float("nan")
    if bad == "bool_current": obs[0]["current_a"] = True
    if bad == "mixed": obs[-1]["run_id"] = "different"
    if bad == "order": obs[0], obs[1] = obs[1], obs[0]
    if bad == "seq": obs[1]["sequence_number"] = 100
    if bad == "orphan": events = events[1:]
    with pytest.raises(ValueError):
        extract_features(obs, events)


@pytest.mark.parametrize("window", [0, 51, True, 60_050])
def test_invalid_window(window):
    with pytest.raises(ValueError):
        extract_features(*session(), window_ms=window)
