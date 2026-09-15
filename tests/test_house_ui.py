from pathlib import Path
import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest


def test_house_views_controls_and_reset():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "simulator_app.py"))
    app.run(timeout=20)
    assert not app.exception
    app.button(key="command_led_01").click().run()
    assert app.session_state.lab.actuators["led_01"]["simulated"] == 1
    app.button(key="lab_step").click().run()
    assert app.session_state.lab.time == 2
    for page in ["Urządzenia", "Scenariusze", "Telemetria", "Eksperymenty", "Makieta"]:
        app.radio(key="lab_page").set_value(page).run(timeout=20)
        assert not app.exception
    app.button(key="lab_reset").click().run()
    assert app.session_state.lab.time == 1
    assert app.session_state.lab.actuators["led_01"]["simulated"] == 0
