"""Train-scaled forecast residuals and causal alarms on a common time grid."""

from dataclasses import dataclass
import math

import numpy as np

from ml.gate_features import SAMPLE_MS

SCORE_VERSION = "gate-residual-rms-1"


def residuals(actual, predicted):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if actual.ndim != 2 or actual.shape[1] != 3 or actual.shape != predicted.shape or not len(actual):
        raise ValueError("Expected aligned nonempty arrays of three channels.")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("This three-channel pilot requires complete finite measurements/predictions.")
    if (not np.isin(actual[:, :2], [0, 1]).all() or (actual[:, 2] < 0).any()
            or (predicted[:, :2] < 0).any() or (predicted[:, :2] > 1).any()):
        raise ValueError("Invalid contact probabilities or measured current.")
    return np.abs(actual - predicted)


@dataclass(frozen=True)
class ResidualScaler:
    scales: tuple

    def __post_init__(self):
        if len(self.scales) != 3 or any(not math.isfinite(v) or v <= 0 for v in self.scales):
            raise ValueError("Three finite positive residual scales required.")

    @classmethod
    def fit(cls, normal_training_actual, normal_training_prediction):
        errors = residuals(normal_training_actual, normal_training_prediction)
        # Numerical floor in each channel's native unit, not a physical noise model.
        rms = np.maximum(np.sqrt(np.mean(errors ** 2, axis=0)), 1e-6)
        return cls(tuple(float(v) for v in rms))

    def scores(self, actual, predicted):
        return (residuals(actual, predicted) / self.scales).max(axis=1).tolist()


def timed_alarms(times, scores, threshold):
    """Three consecutive high samples; gaps/unavailable scores reset persistence."""
    if len(times) != len(scores) or not times or not math.isfinite(threshold):
        raise ValueError("Expected aligned timestamps/scores and finite threshold.")
    result, previous, count = [], None, 0
    for now, score in zip(times, scores):
        if type(now) is not int or now < 0 or now % SAMPLE_MS or (previous is not None and now <= previous):
            raise ValueError("Expected ordered timestamps on the 50 ms grid.")
        if score is not None and not math.isfinite(score):
            raise ValueError("Use None for unavailable scores, never NaN/Infinity.")
        if previous is not None and now - previous != SAMPLE_MS:
            count = 0
        count = count + 1 if score is not None and score > threshold else 0
        result.append(count >= 3)
        previous = now
    return result


def common_labels(full_labels, times):
    """Crop only a fault-free warmup; never silently remove an event or its onset."""
    if not times or any(type(t) is not int for t in times):
        raise ValueError("Missing or invalid evaluation times.")
    start, end = times[0], times[-1]
    if (start < 0 or start % SAMPLE_MS or times != list(range(start, end + 1, SAMPLE_MS))
            or end != (len(full_labels) - 1) * SAMPLE_MS
            or any(type(v) is not bool for v in full_labels)):
        raise ValueError("Evaluation requires a complete aligned suffix of the session.")
    offset = start // SAMPLE_MS
    if any(full_labels[:offset]):
        raise ValueError("Warmup contains events; refusing to drop or truncate them.")
    return full_labels[offset:]
