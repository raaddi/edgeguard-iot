"""Small in-memory simulation session, independent of the interface."""

from collections import deque

from simulator.normal_activity import gas_signal
from simulator.telemetry import build_message, session_id


class SimulationSession:
    def __init__(self, seed: int = 42, device_id: str = "virtual_node_01"):
        self.seed = seed
        self.device_id = device_id
        self.reset()

    def reset(self) -> None:
        self.signal = gas_signal(self.seed)
        self.boot_id = session_id("lesson-01", self.device_id)
        self.history = deque(maxlen=300)
        self.sequence = 0
        self.advance()  # Show the first sample even before playback starts.

    def advance(self) -> dict:
        message = build_message(
            self.device_id, self.boot_id, self.sequence, next(self.signal),
        )
        self.history.append(message)
        self.sequence += 1
        return message
