from dataclasses import asdict

import pytest

from simulator.gate import Gate, GateConfig


def advance(gate, duration=1500):
    return [gate.advance(50) for _ in range(duration // 50)]


def test_command_is_not_feedback_and_motion_takes_time():
    gate = Gate(GateConfig())
    before = gate.read()
    gate.command(110)
    assert gate.read() == before
    first = gate.advance(50)
    assert not first.closed_contact and not first.open_contact
    assert advance(gate)[-1].open_contact
    gate.command(0)
    assert gate.read().open_contact
    assert advance(gate)[-1].closed_contact


def test_mid_motion_reversal_and_endpoints_remain_bounded():
    gate = Gate(GateConfig())
    gate.command(110)
    advance(gate, 300)
    gate.command(0)
    assert advance(gate, 300)[-1].closed_contact
    assert all(r.closed_contact and not r.open_contact for r in advance(gate))


def test_contacts_cannot_distinguish_stall_and_bad_contact_at_rest():
    stalled = Gate(GateConfig(motion_stall=True))
    bad_contact = Gate(GateConfig(open_contact_stuck_low=True))
    for gate in (stalled, bad_contact):
        gate.command(110)
        advance(gate)
    a, b = stalled.read(), bad_contact.read()
    assert (a.closed_contact, a.open_contact) == (b.closed_contact, b.open_contact) == (False, False)
    assert a.current_a > 0.6 and b.current_a < 0.1
    for gate in (stalled, bad_contact):
        gate.command(0)
        assert advance(gate)[-1].closed_contact


def test_reproducibility_missing_current_and_no_hidden_state_in_readings():
    a, b = Gate(GateConfig(), seed=9), Gate(GateConfig(), seed=9)
    c = Gate(GateConfig(measure_current=False), seed=9)
    for gate in (a, b, c):
        gate.command(110)
    assert advance(a) == advance(b)
    readings = advance(c)
    assert all(r.current_a is None for r in readings)
    assert c.read().open_contact == a.read().open_contact
    assert set(asdict(a.read())) == {"closed_contact", "open_contact", "current_a"}
    assert a.read() == a.read()


@pytest.mark.parametrize("value", [-1, 0, 101, 50.0, True])
def test_invalid_timestep_does_not_mutate_state(value):
    gate = Gate(GateConfig())
    before = gate.read()
    with pytest.raises(ValueError):
        gate.advance(value)
    assert gate.read() == before


@pytest.mark.parametrize("value", [-1, 1, 180, 110.0, True])
def test_invalid_command(value):
    with pytest.raises(ValueError):
        Gate(GateConfig()).command(value)


@pytest.mark.parametrize("config", [{"stroke_ms": 0}, {"stroke_ms": 1000.0},
                                    {"measure_current": 1}, {"motion_stall": "false"}])
def test_invalid_config(config):
    with pytest.raises(ValueError):
        GateConfig(**config)
