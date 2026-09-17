"""Run with python -m simulator.desktop."""

import argparse
import sys
from PySide6.QtWidgets import QApplication
from simulator.house import HouseSimulation
from simulator.__main__ import identifier
from simulator.desktop.window import LaboratoryWindow


def main():
    parser = argparse.ArgumentParser(description="EdgeGuard: desktopowe laboratorium SmartHome")
    parser.add_argument("--nodes", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--extra-nodes", type=int, choices=range(10), default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run-id", type=identifier, default="desktop-lab")
    args = parser.parse_args()
    if not 0 <= args.seed <= 2**31 - 1:
        parser.error("Seed must be between 0 and 2147483647.")
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    window = LaboratoryWindow(HouseSimulation(args.seed, args.nodes, args.extra_nodes, args.run_id))
    available = app.primaryScreen().availableGeometry()
    window.resize(min(1440, available.width() - 40), min(940, available.height() - 40))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
