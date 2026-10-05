"""Bounded experiment settings for the shared offline gate pilot."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GateSessionSettings:
    duration_ms: int = 8000
    schedule: tuple = ((1000, 110), (5000, 0))
    stroke_bounds_ms: tuple = (900, 1300)
    nominal_delays_ms: tuple = (50, 100, 150)
    fault_delay_ms: int = 1200

    def __post_init__(self):
        def grid(value, low, high):
            return type(value) is int and low <= value <= high and value % 50 == 0
        if not grid(self.duration_ms, 8000, 60000):
            raise ValueError("Duration must be 8000..60000 ms on the 50 ms grid.")
        if (not isinstance(self.stroke_bounds_ms, tuple) or len(self.stroke_bounds_ms) != 2
                or any(not grid(v, 500, 5000) for v in self.stroke_bounds_ms)
                or self.stroke_bounds_ms[0] > self.stroke_bounds_ms[1]):
            raise ValueError("Invalid stroke range.")
        if (not isinstance(self.nominal_delays_ms, tuple) or not self.nominal_delays_ms
                or any(not grid(v, 50, 2500) for v in self.nominal_delays_ms)
                or not grid(self.fault_delay_ms, 50, 2500)):
            raise ValueError("Invalid delivery delay; command expiry is 3000 ms.")
        if not isinstance(self.schedule, tuple) or len(self.schedule) > 64:
            raise ValueError("Expected a bounded tuple schedule.")
        previous = -1
        last_allowed = self.duration_ms - max((*self.nominal_delays_ms, self.fault_delay_ms))
        for entry in self.schedule:
            if (not isinstance(entry, tuple) or len(entry) != 2
                    or not grid(entry[0], 1000, last_allowed) or entry[0] <= previous
                    or type(entry[1]) is not int or entry[1] not in (0, 110)):
                raise ValueError("Commands must be ordered after warmup and answered within the session.")
            previous = entry[0]
