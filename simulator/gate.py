"""Illustrative gate dynamics, independent of transport, GUI and ML.

The private angle is generator state, never a measured position. Current levels
and contact thresholds are assumptions, not a calibrated servo model.
"""

from dataclasses import dataclass
import random

MODEL_VERSION = "illustrative-gate-v1"
OPEN_DEGREES = 110


@dataclass(frozen=True)
class GateConfig:
    stroke_ms: int = 1000
    motion_stall: bool = False
    open_contact_stuck_low: bool = False
    measure_current: bool = True

    def __post_init__(self):
        if type(self.stroke_ms) is not int or not 500 <= self.stroke_ms <= 5000:
            raise ValueError("stroke_ms must be an integer in 500..5000.")
        for flag in (self.motion_stall, self.open_contact_stuck_low, self.measure_current):
            if type(flag) is not bool:
                raise ValueError("Gate flags must be boolean.")


@dataclass(frozen=True)
class GateReading:
    closed_contact: bool
    open_contact: bool
    current_a: float | None


class Gate:
    """A jam blocks opening at half travel; closing is allowed in this profile."""

    def __init__(self, config: GateConfig, *, seed: int = 42):
        if type(seed) is not int:
            raise ValueError("seed must be an integer.")
        self.config = config
        self._rng = random.Random(seed)
        self._angle = 0.0
        self._target = 0
        self._reading = self._observe()

    def command(self, target: int) -> None:
        if type(target) is not int or target not in (0, OPEN_DEGREES):
            raise ValueError("Gate target must be 0 or 110 degrees.")
        self._target = target
        # Accepting a target does not move the mechanism or invent a new sample.

    def advance(self, elapsed_ms: int) -> GateReading:
        if type(elapsed_ms) is not int or not 1 <= elapsed_ms <= 100:
            raise ValueError("Use an integer integration step in 1..100 ms.")
        distance = OPEN_DEGREES * elapsed_ms / self.config.stroke_ms
        if self._target > self._angle:
            stop = OPEN_DEGREES / 2 if self.config.motion_stall else self._target
            self._angle = min(stop, self._angle + distance)
        elif self._target < self._angle:
            self._angle = max(self._target, self._angle - distance)
        self._reading = self._observe()
        return self._reading

    def read(self) -> GateReading:
        """Repeated reads of the same sample do not change noise or dynamics."""
        return self._reading

    def _observe(self) -> GateReading:
        stalled = (self.config.motion_stall and self._target == OPEN_DEGREES
                   and self._angle >= OPEN_DEGREES / 2)
        moving = abs(self._target - self._angle) > 1e-9
        level = 0.70 if stalled else 0.28 if moving else 0.04
        # Consume one noise draw even with this channel disabled: paired runs
        # keep identical dynamics and sample sequence for sensor ablations.
        current = round(level + self._rng.uniform(-0.02, 0.02), 4)
        return GateReading(
            closed_contact=self._angle <= 2,
            open_contact=self._angle >= 108 and not self.config.open_contact_stuck_low,
            current_a=current if self.config.measure_current else None,
        )
