"""Exercise playback state through Streamlit's real script runner."""

from itertools import islice
from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

from simulator.normal_activity import gas_signal
from simulator.session import SimulationSession
from simulator.telemetry import SENSOR_ID


def test_session_matches_generator_resets_and_bounds_history():
    session = SimulationSession(seed=42)
    for _ in range(399):
        session.advance()
    assert len(session.history) == 300
    assert session.sequence == 400
    expected = list(islice(gas_signal(42), 400))
    assert [m["sensors"][SENSOR_ID]["value"] for m in session.history] == expected[-300:]
    session.reset()
    assert session.sequence == 1
    assert session.history[0]["sensors"][SENSOR_ID]["value"] == expected[0]


def test_app_step_pause_reset_and_configuration():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "simulator_app.py"))
    app.run(timeout=20)
    assert not app.exception
    assert app.session_state.simulation.sequence == 1
    app.button(key="step").click().run()
    assert app.session_state.simulation.sequence == 2
    app.run()
    assert app.session_state.simulation.sequence == 2  # Rendering while paused creates no data.
    app.button(key="play").click().run()
    assert app.session_state.running
    assert app.button(key="step").disabled
    app.button(key="play").click().run()
    assert not app.session_state.running
    app.button(key="reset").click().run()
    assert app.session_state.simulation.sequence == 1
    app.number_input[0].set_value(43)
    app.text_input[0].set_value("virtual_node_02")
    app.button(key="apply").click().run()
    assert app.session_state.simulation.seed == 43
    assert app.session_state.simulation.device_id == "virtual_node_02"
    app.text_input[0].set_value("bad/+id")
    app.button(key="apply").click().run()
    assert app.error
    assert app.session_state.simulation.device_id == "virtual_node_02"
    assert not app.exception
