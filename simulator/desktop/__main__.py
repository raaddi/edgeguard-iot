"""Run with python -m simulator.desktop."""

import argparse
import sys
from PySide6.QtWidgets import QApplication
from simulator.house import HouseSimulation
from simulator.desktop.window import GarageWindow


def main():
    parser = argparse.ArgumentParser(description="EdgeGuard: prototyp garażu w Qt")
    parser.add_argument("--nodes", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--extra-nodes", type=int, choices=range(10), default=0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    window = GarageWindow(HouseSimulation(args.seed, args.nodes, args.extra_nodes, "qt-garage"))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
