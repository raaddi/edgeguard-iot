import pytest

from ml.gate_response_timeout import ResponseTimeout


def monitor():
    return ResponseTimeout(sent_ms=1000, predicted_ms=100, margin_ms=50)


def test_waits_through_deadline_and_emits_once_on_observed_tick():
    timer = monitor()
    assert timer.deadline_ms == 1150
    for now in (1000, 1100, 1150):
        assert not timer.advance(now)
    assert timer.advance(1200)
    assert timer.alarm_ms == 1200
    assert not timer.advance(1200)
    assert not timer.advance(1300)
    assert not timer.closed


@pytest.mark.parametrize("now", [1000, 1100, 1150])
@pytest.mark.parametrize("terminal", ["completed", "censored"])
def test_terminal_event_by_deadline_stops_wait_without_alarm(now, terminal):
    timer = monitor()
    assert not timer.advance(now, **{terminal: True})
    assert timer.closed
    assert not timer.advance(5000)
    assert timer.alarm_ms is None


@pytest.mark.parametrize("terminal", ["completed", "censored"])
def test_late_terminal_event_preserves_timeout(terminal):
    timer = monitor()
    assert timer.advance(1200, **{terminal: True})
    assert timer.closed
    assert timer.alarm_ms == 1200
    assert not timer.advance(1500)


def test_completion_after_emission_does_not_emit_again():
    timer = monitor()
    assert timer.advance(1200)
    assert not timer.advance(1300, completed=True)
    assert timer.closed
    assert timer.alarm_ms == 1200


def test_ack_and_contact_have_independent_lifecycles():
    ack = monitor()
    contact = ResponseTimeout(sent_ms=1000, predicted_ms=1000, margin_ms=50)
    assert not ack.advance(1100, completed=True)
    assert not contact.advance(1100)
    assert contact.advance(2100)
    assert ack.alarm_ms is None


def test_invalid_clock_and_flags_do_not_mutate_monitor():
    timer = monitor()
    timer.advance(1100)
    for now, flags in ((1050, {}), (1200, {"completed": 1}),
                       (1200, {"completed": True, "censored": True})):
        with pytest.raises(ValueError):
            timer.advance(now, **flags)
    assert timer.alarm_ms is None
    assert not timer.closed
    assert not timer.advance(1150, completed=True)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "10", None])
@pytest.mark.parametrize("field", ["sent_ms", "predicted_ms", "margin_ms"])
def test_rejects_invalid_configuration(field, value):
    kwargs = dict(sent_ms=1000, predicted_ms=100, margin_ms=50)
    kwargs[field] = value
    with pytest.raises(ValueError):
        ResponseTimeout(**kwargs)


@pytest.mark.parametrize("now", [-1, float("nan"), float("inf"), True, "10", None])
def test_rejects_invalid_observation_time(now):
    timer = monitor()
    with pytest.raises(ValueError):
        timer.advance(now)
    assert timer.alarm_ms is None
    assert not timer.closed


def test_zero_duration_and_fractional_deadline():
    timer = ResponseTimeout(sent_ms=0, predicted_ms=0, margin_ms=0)
    assert not timer.advance(0)
    assert timer.advance(0.1)
    other = ResponseTimeout(sent_ms=1.5, predicted_ms=2.5, margin_ms=0.25)
    assert not other.advance(4.25)
    assert other.advance(4.5)


def test_rejects_overflowing_deadline():
    with pytest.raises(ValueError):
        ResponseTimeout(sent_ms=1e308, predicted_ms=1e308, margin_ms=0)
