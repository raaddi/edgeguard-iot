import copy
import json
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from simulator.desktop.ml_timeline import MAX_BYTES, read_timeline, validate_timeline
from simulator.desktop.window import LaboratoryWindow


@pytest.fixture
def timeline():
    return {"timeline_version": "gate-ml-view-1", "run_id": "gui-check", "logical_ms": [1000, 1050, 1100, 1200],
            "actual": [[1, 0, .2], [0, 0, .3], [0, 1, .4], [0, 1, .1]],
            "predicted": [[.9, .1, .21], [.1, .2, .32], [.1, .8, .39], [.1, .9, .12]],
            "scaled_residuals": [[1, 2, 3], [2, 3, 1], [2, 1, 3], [1, 2, 3]],
            "scores": {"gru": [3, 3, None, 3], "temporal_rules": [1, 2, 3, 4]},
            "thresholds": {"gru": 2.0, "temporal_rules": 2.5},
            "method_alarms": {"gru": [False, False, False, True], "temporal_rules": [False, False, True, False]},
            "labels": [False, True, True, False], "pending_commands": [0, 1, 1, 0],
            "commands": [{"logical_ms": 1050, "value": 110}], "source": "synthetic", "model_version": "gate-gru-1"}


@pytest.mark.parametrize("change", [
    lambda t: t.update(logical_ms=[1000, 1000, 1100, 1200]),
    lambda t: t.update(actual=[[1, 0, float('nan')]] * 4),
    lambda t: t["scores"].update(gru=[1]),
    lambda t: t["thresholds"].update(gru=float('inf')),
    lambda t: t["method_alarms"].update(gru=[0] * 4),
    lambda t: t.update(commands=[{"logical_ms": 1050, "value": 90}]),
    lambda t: t.update(timeline_version="unknown"),
    lambda t: t.update(pending_commands=[False] * 4),
    lambda t: t.update(predicted=[[2, 0, 0]] * 4),
])
def test_invalid_timelines_are_rejected(timeline, change):
    change(timeline)
    with pytest.raises(ValueError):
        validate_timeline(timeline)


def test_legacy_diagnostics_and_file_size_are_supported(timeline, tmp_path):
    legacy = copy.deepcopy(timeline)
    legacy.pop("timeline_version")
    legacy["scores"], legacy["alarms"], legacy["threshold"] = [1.0] * 4, [False] * 4, 2.0
    legacy.pop("method_alarms")
    legacy.pop("thresholds")
    legacy["commands"] = [{"kind": "command_sent", "logical_ms": 1050, "message": {"value": 110}},
                          {"kind": "command_result", "logical_ms": 1100, "message": {"status": "accepted"}}]
    assert validate_timeline(legacy)["commands"] == [{"logical_ms": 1050, "value": 110}]
    path = tmp_path / "large.json"
    path.write_bytes(b" " * (MAX_BYTES + 1))
    with pytest.raises(ValueError, match="4 MiB"):
        read_timeline(path)


def wait_load(view):
    for _ in range(200):
        QApplication.processEvents()
        if view.worker is None:
            return
        QTest.qWait(10)
    pytest.fail("Timeline worker did not complete")


@pytest.mark.parametrize("invalid_json", ["{}", "[" * 2000 + "0" + "]" * 2000])
def test_real_series_method_selection_cursor_and_bad_file_preserve_state(timeline, tmp_path, invalid_json):
    app = QApplication.instance() or QApplication([])
    if not QFontDatabase.families() and os.name == "nt":
        for font in ("segoeui.ttf", "seguisb.ttf", "consola.ttf"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)
    path = tmp_path / "valid.json"
    path.write_text(json.dumps(timeline))
    window = LaboratoryWindow()
    window.show()
    window.toggle()
    assert window.timer.isActive()
    window.source.setCurrentIndex(2)
    assert not window.timer.isActive()
    window.toggle()
    assert not window.timer.isActive()
    view = window.ml_view
    try:
        view.load_timeline(path)
        wait_load(view)
        assert view.measurement.series()[0][0] == [0, 0, 1, 1]
        assert view.measurement.series()[1][0] == [.1, .2, .8, .9]
        assert not view.truth.isChecked()
        assert "Etykieta eksperymentu:" not in view.evidence.toPlainText()
        view.channel.setCurrentIndex(2)
        view.slider.setValue(1)
        assert "Pomiar: 0.3000" in view.evidence.toPlainText()
        assert "Prognoza GRU: 0.3200" in view.evidence.toPlainText()
        view.method.setCurrentIndex(view.method.findData("temporal_rules"))
        assert view.score.series()[0][0] == [1, 2, 3, 4]
        assert view.card_values[2].text() == "2.500"
        QTest.mouseClick(view.truth, Qt.MouseButton.LeftButton)
        assert "Etykieta eksperymentu: True" in view.evidence.toPlainText()
        view.slider.setValue(0)
        view.command_cursor(0, 0)
        assert view.slider.value() == 1
        assert not view.grab().isNull()
        prior = view.data
        bad = tmp_path / "invalid.json"
        bad.write_text(invalid_json)
        view.load_timeline(bad)
        wait_load(view)
        assert view.data is prior
        assert "Nie wczytano" in view.status.text()
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
