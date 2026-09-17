"""Exercise real Qt signals and the shared simulator without a display server."""

import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from simulator.desktop.window import GarageWindow
from simulator.house import HouseSimulation


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(application):
    widget = GarageWindow()
    widget.show()
    application.processEvents()
    yield widget
    widget.dirty = False
    widget.close()


def click(button):
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)


def test_canvas_selection_controls_and_keyboard_alternative(window):
    QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=window.canvas.device_center("led_01"))
    assert window.current == "led_01"
    click(window.command_button)
    assert window.sim.actuators["led_01"]["simulated"] == 1
    window.devices.setCurrentIndex(window.devices.findData("servo_01"))
    assert window.canvas.current == "servo_01"
    click(window.command_button)
    assert window.sim.actuators["servo_01"]["simulated"] == 110
    assert not window.canvas.grab().isNull()


def test_scenarios_offline_gap_and_export_replay(window, tmp_path):
    click(window.inject_button)
    click(window.single_step)
    assert window.sim.actuators["fan_01"]["simulated"] == 1
    window.scenario.setCurrentIndex(window.scenario.findData("fan_failure"))
    click(window.inject_button)
    click(window.single_step)
    assert {"rule": "actuator_mismatch", "target": "fan_01"} in window.sim.alerts
    window.scenario.setCurrentIndex(window.scenario.findData("node_offline"))
    window.duration.setValue(2)
    click(window.inject_button)
    click(window.single_step)
    window.select_device("servo_01")
    click(window.command_button)
    assert window.sim.actions[-1]["accepted"] is False
    assert window.plot.samples()[-1][1] is None
    click(window.single_step)
    click(window.single_step)
    assert [v is None for _, v in window.plot.samples()][-3:] == [True, True, False]
    path = tmp_path / "run.json"
    window.save_to(path)
    exported = json.loads(path.read_text(encoding="utf-8"))
    assert HouseSimulation.replay(exported).export(window.version) == exported
    assert not window.dirty


@pytest.mark.parametrize("nodes", [1, 2, 3])
def test_node_mapping_is_taken_from_model(application, nodes):
    widget = GarageWindow(HouseSimulation(node_count=nodes, extra_nodes=2))
    widget.scenario.setCurrentIndex(widget.scenario.findData("node_offline"))
    assert widget.scenario_target() == widget.sim.room_nodes["garage"]
    click(widget.inject_button)
    widget.step()
    assert len(widget.sim.nodes) == nodes + 2
    assert not widget.sim.nodes[widget.sim.room_nodes["garage"]]
    widget.dirty = False
    widget.close()


def test_clock_pause_and_model_limit(window):
    click(window.play)
    assert window.timer.isActive() and not window.single_step.isEnabled()
    window.timer.setInterval(10)
    QTest.qWait(50)
    click(window.play)
    assert not window.timer.isActive() and window.sim.time > 1
    window.sim.MAX_STEPS = window.sim.time
    click(window.play)
    window.step()
    assert not window.timer.isActive()
    assert "LIMIT" in window.log.toPlainText()
