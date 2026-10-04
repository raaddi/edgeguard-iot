"""Descriptive diagnostics at a frozen threshold; no model tuning."""

import math

from ml.gate_evaluation import alarms, intervals
from ml.gate_features import SAMPLE_MS
from ml.gate_residuals import timed_alarms


def diagnose_events(times, scores, labels, threshold):
    """Explain misses without resetting alarm state at truth boundaries."""
    if (not times or len(times) != len(labels) or len(times) != len(scores)
            or any(type(v) is not bool for v in labels)
            or any(v is None or not math.isfinite(v) for v in scores)
            or times != list(range(times[0], times[-1] + SAMPLE_MS, SAMPLE_MS))):
        raise ValueError("Diagnostics require complete aligned labels and finite scores.")
    flags = timed_alarms(times, scores, threshold)
    starts = {a for a, _ in intervals(flags)}
    sensitivity = {str(p): {a for a, _ in intervals(alarms(scores, threshold, persistence=p))}
                   for p in (1, 3, 5)}
    result = []
    for a, b in intervals(labels):
        matched = sorted(i for i in starts if a <= i < b)
        high = [s > threshold for s in scores[a:b]]
        longest = max((end - start for start, end in intervals(high)), default=0)
        if matched:
            reason = "detected"
        elif not any(high):
            reason = "below_threshold"
        elif any(flags[a:b]):
            reason = "alarm_started_before_event"
        else:
            reason = "insufficient_persistence_within_event"
        result.append({"start_ms": times[a], "last_sample_ms": times[b - 1],
                       "samples": b - a, "reason": reason,
                       "peak_score": max(scores[a:b]), "threshold": threshold,
                       "exceeding_samples": sum(high), "longest_high_run_samples": longest,
                       "alarm_start_ms": times[matched[0]] if matched else None,
                       "detected_by_persistence": {
                           p: any(a <= i < b for i in indices)
                           for p, indices in sensitivity.items()}})
    return result
