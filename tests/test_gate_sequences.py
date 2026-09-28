from copy import deepcopy

import pytest

from ml.gate_sequences import iter_sequences
from simulator.gate_pilot import simulate_session


def session(**kwargs):
    return simulate_session(seed=42, case="normal", run_id="sequence-test", **kwargs)[:2]


def test_forecast_is_strictly_after_history_and_has_only_sensor_targets():
    obs, events = session()
    rows = list(iter_sequences(obs, events))
    assert len(rows) == 141
    first = rows[0]
    assert first["input_times_ms"] == list(range(0, 1000, 50))
    assert first["prediction_ms"] == 950 and first["target_ms"] == 1000
    assert set(first["y"]) == {"closed_contact", "open_contact", "current_a"}
    assert first["y"] == {k: obs[20][k] for k in first["y"]}
    # The command at 1000 ms is not available to the forecast made at 950 ms.
    assert first["x"][-1]["last_command_degrees"] is None
    assert rows[1]["x"][-1]["last_command_degrees"] == 110
    for row in rows:
        assert len(row["x"]) == 20
        assert row["target_ms"] == row["prediction_ms"] + 50
        assert all(t <= row["prediction_ms"] for t in row["input_times_ms"])
        assert not {"case", "seed", "profile", "run_id", "y"} & row["x"][0].keys()


def test_future_target_changes_cannot_change_inputs_and_prefix_is_stable():
    obs, events = session()
    full = list(iter_sequences(obs, events))
    prefix = list(iter_sequences(obs[:41], [e for e in events if e["logical_ms"] <= 2000]))
    assert prefix == [row for row in full if row["target_ms"] <= 2000]
    changed = deepcopy(obs)
    changed[20]["current_a"] = 99.0
    changed[20]["open_contact"] = True
    after = next(iter_sequences(changed, events))
    assert after["x"] == full[0]["x"] and after["y"] != full[0]["y"]


def test_no_window_crosses_gaps_in_history_or_forecast_interval():
    obs, events = session()
    obs = [o for o in obs if o["logical_ms"] != 2000]
    rows = list(iter_sequences(obs, events, history_samples=3, horizon_samples=4))
    assert rows
    assert all(not r["input_times_ms"][0] < 2000 < r["target_ms"] for r in rows)
    assert all(r["target_ms"] - r["prediction_ms"] == 200 for r in rows)
    assert any(r["input_times_ms"][0] == 2050 for r in rows)


def test_missing_current_stays_null_and_sessions_do_not_share_history():
    busy = list(iter_sequences(*session()))
    idle = list(iter_sequences(*session(profile="idle", measure_current=False)))
    assert busy and idle
    assert all(r["y"]["current_a"] is None for r in idle)
    assert all(x["current_a"] is None and x["last_command_degrees"] is None
               for r in idle for x in r["x"])
    assert idle[0]["input_times_ms"][0] == 0
    assert list(iter_sequences(*session(), history_samples=200)) == []


def test_mixed_sessions_are_rejected_and_returned_windows_are_independent():
    obs, events = session()
    rows = list(iter_sequences(obs, events))
    before = deepcopy(rows[1])
    rows[0]["x"][1]["current_a"] = 99
    assert rows[1] == before
    obs[-1]["run_id"] = "other-session"
    with pytest.raises(ValueError, match="Mixed"):
        list(iter_sequences(obs, events))


@pytest.mark.parametrize("name", ["history_samples", "horizon_samples"])
@pytest.mark.parametrize("value", [0, True, 1.5, 201])
def test_invalid_configuration(name, value):
    with pytest.raises(ValueError, match=name):
        list(iter_sequences(*session(), **{name: value}))
