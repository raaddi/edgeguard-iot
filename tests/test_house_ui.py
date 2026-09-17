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
    app.selectbox(key="selected_room").set_value("yard").run()
    app.selectbox(key="actuator_yard").set_value("servo_03").run()
    app.button(key="command_servo_03").click().run()
    assert app.session_state.lab.actuators["servo_03"]["simulated"] == 110
    assert not app.exception
    app.button(key="lab_reset").click().run()
    assert app.session_state.lab.time == 1
    assert app.session_state.lab.actuators["led_01"]["simulated"] == 0


def test_console_scenario_offline_and_replay():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "simulator_app.py")).run(timeout=20)
    app.button(key="inject_scenario").click().run()
    assert app.session_state.lab.scenarios[-1]["target"] == "gas_01"
    app.button(key="lab_step").click().run()
    assert app.session_state.lab.actuators["fan_01"]["simulated"] == 1
    app.selectbox(key="scenario_kind").set_value("fan_failure").run()
    app.button(key="inject_scenario").click().run()
    app.button(key="lab_step").click().run()
    assert {"rule": "actuator_mismatch", "target": "fan_01"} in app.session_state.lab.alerts
    app.selectbox(key="scenario_kind").set_value("node_offline").run()
    app.button(key="inject_scenario").click().run()
    app.button(key="lab_step").click().run()
    app.button(key="command_led_01").click().run()
    assert app.session_state.lab.actions[-1]["accepted"] is False
    assert app.session_state.lab.suppressed_messages > 0
    replay_button = next(b for b in app.button if b.label == "Sprawdź odtwarzalność przebiegu")
    replay_button.click().run()
    assert any("Odtworzono identyczny" in s.value for s in app.success)
    assert not app.exception


def test_console_topology_change_and_virtual_controls():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "simulator_app.py")).run(timeout=20)
    next(n for n in app.number_input if n.label.startswith("Węzły makiety")).set_value(1)
    next(n for n in app.number_input if n.label == "Dodatkowe węzły wirtualne").set_value(2)
    app.button(key="new_run").click().run()
    app.selectbox(key="selected_room").set_value("virtual").run()
    app.selectbox(key="signal_virtual").set_value("virtual_gas_02").run()
    app.button(key="inject_scenario").click().run()
    assert app.session_state.lab.scenarios[-1]["target"] == "virtual_gas_02"
    app.button(key="lab_step").click().run()
    assert app.session_state.lab.sensors["virtual_gas_02"]["value"] > 0.5
    next(n for n in app.number_input if n.label == "Dodatkowe węzły wirtualne").set_value(0)
    app.button(key="new_run").click().run()
    assert app.session_state.selected_room == "garage"
    assert not app.exception
