"""Fixed synthetic gate conditions shared by offline research exporters."""

from simulator.gate_session import GateSessionSettings

CYCLES = ((2000, 110), (7000, 0), (14000, 110), (20000, 0))
CONDITIONS = {
    "cycles": GateSessionSettings(30000, CYCLES, (900, 1500), (50, 100, 150, 200)),
    "repeats": GateSessionSettings(30000, ((2000, 110), (2400, 110), (7000, 0),
        (14000, 110), (14400, 110), (20000, 0)), (900, 1500), (50, 100, 150, 200)),
    "idle": GateSessionSettings(30000, (), (900, 1500), (50, 100, 150, 200)),
    "slow": GateSessionSettings(30000, CYCLES, (1600, 2000), (250, 300, 350)),
    "reversals": GateSessionSettings(30000, ((2000, 110), (2400, 0), (5000, 110),
        (5400, 110), (9000, 0), (14000, 110), (14500, 0), (19000, 110), (24000, 0)),
        (900, 1500), (50, 100, 150, 200)),
}
CALIBRATION_CONDITIONS = ("cycles", "repeats", "idle")
