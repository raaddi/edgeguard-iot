"""An illustrative signal, not a calibrated MQ-9 sensor model."""

from collections.abc import Iterator
from random import Random


def gas_signal(seed: int) -> Iterator[float]:
    """Yield a repeatable signal with small changes and a return to baseline."""
    rng = Random(seed)
    baseline = 0.2
    value = baseline
    while True:
        # A little memory, a pull towards the baseline, and bounded noise.
        value += 0.1 * (baseline - value) + rng.uniform(-0.01, 0.01)
        value = min(1.0, max(0.0, value))
        yield round(value, 6)
