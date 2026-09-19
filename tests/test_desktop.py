"""Exercise real Qt signals and the shared simulator without a display server."""

import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from simulator.desktop.window import LaboratoryWindow
from simulator.house import HouseSimulation


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(application):
    widget = LaboratoryWindow()
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
    widget = LaboratoryWindow(HouseSimulation(node_count=nodes, extra_nodes=2))
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


def test_whole_house_selection_linked_channels_and_virtual_nodes(window):
    window.replace_simulation(HouseSimulation(extra_nodes=2))
    assert set(window.canvas.areas()) == set(window.sim.components)
    for cid in window.sim.components:
        QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=window.canvas.device_center(cid))
        assert window.current == cid
        assert window.plot.component == cid
    window.focus_room("yard")
    assert set(window.canvas.areas()) == {"led_08", "led_09", "led_10", "servo_03", "servo_04", "servo_06"}
    window.select_device("servo_06")
    click(window.command_button)
    assert window.sim.actuators["servo_06"]["simulated"] == 110
    window.select_device("virtual_gas_02")
    assert window.canvas.room == "virtual"
    click(window.inject_button)
    click(window.single_step)
    assert window.sim.sensors["virtual_gas_02"]["value"] > 0.5
    window.replace_simulation(HouseSimulation())
    assert window.plot.component in window.sim.sensors
    assert window.current == "gas_01"
    window.plot.samples()


def test_data_panels_and_search(window):
    click(window.inject_button)
    click(window.single_step)
    window.tabs.setCurrentIndex(2)
    assert window.scenarios_table.item(0, 2).text() == "aktywne"
    window.tabs.setCurrentIndex(3)
    assert window.rules_table.item(0, 0).text() == "gas_01"
    window.tabs.setCurrentIndex(4)
    assert window.nodes_table.rowCount() == 3
    window.tabs.setCurrentIndex(5)
    assert '"schema_version": "1.0"' in window.raw.toPlainText()
    window.tabs.setCurrentIndex(6)
    assert window.sim.run_id in window.manifest.toPlainText()
    window.search.setText("servo_06")
    assert not window.tree_items["servo_06"].isHidden()
    assert window.tree_items["gas_01"].isHidden()
    window.search.clear()
    assert not window.tree_items["gas_01"].isHidden()


def finish_worker(window):
    for _ in range(500):
        QTest.qWait(10)
        if window.worker is None:
            return
    pytest.fail("Replay worker did not finish")


def test_async_import_verify_and_bad_file_preserve_session(window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from PySide6.QtCore import QThread
    window.select_device("servo_06")
    click(window.command_button)
    click(window.single_step)
    path = tmp_path / "session.json"
    window.save_to(path)
    expected = window.sim.snapshot()
    window.replace_simulation(HouseSimulation())
    window.start_replay(str(path), from_file=True)
    assert not window.centralWidget().isEnabled()
    finish_worker(window)
    assert window.sim.snapshot() == expected
    assert window.centralWidget().isEnabled()
    assert window.thread() == QThread.currentThread()
    window.verify_replay()
    finish_worker(window)
    assert "WERYFIKACJA" in window.log.toPlainText()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    path.write_text('{"broken": true}', encoding="utf-8")
    window.start_replay(str(path), from_file=True)
    finish_worker(window)
    assert warnings and window.sim.snapshot() == expected


def test_cancel_reset_preserves_unsaved_state(window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    click(window.single_step)
    old = window.sim
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    window.reset_dialog()
    assert window.sim is old and window.dirty
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    window.reset_dialog()
    assert window.sim.time == 1 and not window.dirty


def test_all_charts_share_clock_and_preserve_offline_gaps(window):
    assert window.chart_mode.currentIndex() == 0
    assert set(window.all_plots.plots) == set(window.sim.components)
    assert len(window.all_plots.plots) == 24
    window.select_device("gas_04")
    assert window.chart_stack.currentWidget() is window.all_plots
    window.chart_mode.setCurrentIndex(1)
    assert window.chart_stack.currentWidget() is window.plot
    assert window.plot.component == "gas_04"
    window.chart_mode.setCurrentIndex(0)
    offline_node = window.sim.components["gas_01"]["node"]
    window.perform(window.sim.inject, "node_offline", offline_node, 2)
    for _ in range(3):
        click(window.single_step)
    timelines = []
    for cid, plot in window.all_plots.plots.items():
        samples = plot.samples()
        timelines.append([t for t, _ in samples])
        offline = window.sim.components[cid]["node"] == offline_node
        assert [value is None for _, value in samples] == [False, offline, offline, False]
    assert all(times == timelines[0] for times in timelines)



def test_actuator_charts_show_telemetry_not_unsent_commands(window):
    lamp = window.all_plots.plots["led_01"]
    servo = window.all_plots.plots["servo_01"]
    fan = window.all_plots.plots["fan_01"]
    window.select_device("led_01")
    click(window.command_button)
    # The model has changed, but no new telemetry has been emitted yet.
    assert lamp.samples()[-1][1] == lamp.samples("commanded")[-1][1] == 0
    window.select_device("servo_01")
    click(window.command_button)
    window.perform(window.sim.inject, "gas_spike", "gas_01", 3)
    window.perform(window.sim.inject, "fan_failure", "fan_01", 3)
    click(window.single_step)
    assert lamp.samples()[-1][1] == lamp.samples("commanded")[-1][1] == 1
    assert servo.samples()[-1][1] == servo.samples("commanded")[-1][1] == 110
    assert servo.scale == 180 and lamp.scale == fan.scale == 1
    assert fan.samples("commanded")[-1][1] == 1
    assert fan.samples()[-1][1] == 0
    assert "Zadane: ON" in fan.status_text() and "raport: OFF" in fan.status_text()
    # An explicitly unavailable report must not be replaced by commanded/model state.
    message = next(m for m in reversed(window.sim.history) if "servo_01" in m["actuators"])
    message["actuators"]["servo_01"].update(reported=None, feedback="unavailable")
    assert servo.samples()[-1][1] is None
    assert servo.samples("commanded")[-1][1] == 110
    assert "raport: —" in servo.status_text()


def test_chart_groups_focus_and_enlargement_preserve_simulation(window, application):
    assert window.channels.count() == 24
    assert window.chart_group.itemText(0) == "Wszystkie (24)"
    window.chart_group.setCurrentIndex(window.chart_group.findData("servo"))
    assert all(group.isHidden() == (kind != "servo") for kind, group in window.all_plots.groups.items())
    window.select_device("servo_06")
    window.chart_mode.setCurrentIndex(1)
    assert window.plot.component == "servo_06"
    click(window.expand_charts)
    assert window.top_panel.isHidden()
    click(window.single_step)
    assert window.sim.time == 2
    click(window.expand_charts)
    assert not window.top_panel.isHidden()
    window.chart_mode.setCurrentIndex(0)
    window.chart_group.setCurrentIndex(0)
    assert all(not group.isHidden() for group in window.all_plots.groups.values())
    window.replace_simulation(HouseSimulation(extra_nodes=2))
    assert window.chart_group.itemText(0) == "Wszystkie (26)"
    assert window.channels.count() == 26
    # Old, evicted telemetry is missing, never filled from current model state.
    window.sim.history.clear()
    assert all(plot.samples() == [(0, None)] for plot in window.all_plots.plots.values())
    application.processEvents()
    assert not window.all_plots.grab().isNull()


def test_chart_grid_rebuilds_for_new_and_restored_topologies(window):
    sim = HouseSimulation(node_count=1, extra_nodes=9)
    sim.step()
    window.replace_simulation(sim)
    assert len(window.all_plots.plots) == 33
    assert all(plot.sim is sim for plot in window.all_plots.plots.values())
    assert window.all_plots.plots["virtual_gas_09"].samples()[-1][0] == 1
    window.replace_simulation(HouseSimulation.replay(sim.export()))
    assert len(window.all_plots.plots) == 33
    window.replace_simulation(HouseSimulation())
    assert set(window.all_plots.plots) == set(window.sim.components)
