"""Render repeatable README screenshots from the real Qt simulator widgets.

Run from the repository root with the environment's Python. The output contains
only curated UI images; experiment data and archives are not exported.
"""

import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from simulator.desktop.window import LaboratoryWindow
from simulator.house import HouseSimulation


def capture(window, application, path):
    for _ in range(3):
        application.processEvents()
    window.refresh()
    application.processEvents()
    if not window.grab().save(str(path)):
        raise RuntimeError(f"Cannot save screenshot: {path}")
    print(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/images")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    application = QApplication([])
    application.setStyle("Fusion")
    # Offscreen Windows sessions can lack the system font registration. No font
    # files are copied or bundled; other systems use Qt's available fallback.
    for name in ("segoeui.ttf", "seguisb.ttf", "consola.ttf"):
        font = Path("C:/Windows/Fonts") / name
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    window = LaboratoryWindow(HouseSimulation(seed=42, run_id="desktop-demo"))
    window.resize(1600, 1060)
    window.show()
    try:
        for component in ("led_01", "led_03", "led_07"):
            window.select_device(component)
            window.command_button.click()
        window.select_device("servo_01")
        window.command_button.click()
        for _ in range(60):
            window.step()
        # One full chart row is visible while the lower groups remain scrollable.
        window.vertical_splitter.setSizes([400, 355])
        window.select_device("gas_04")
        capture(window, application, args.output / "desktop-house.png")

        window.select_device("gas_01")
        window.scenario.setCurrentIndex(window.scenario.findData("gas_spike"))
        window.inject_button.click()
        window.scenario.setCurrentIndex(window.scenario.findData("fan_failure"))
        window.inject_button.click()
        for _ in range(12):
            window.step()
        window.focus_room("garage")
        window.select_device("fan_01")
        window.chart_mode.setCurrentIndex(1)
        window.vertical_splitter.setSizes([440, 315])
        capture(window, application, args.output / "desktop-garage.png")
    finally:
        window.pause()
        window.dirty = False
        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
