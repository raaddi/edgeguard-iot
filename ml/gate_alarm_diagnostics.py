"""Descriptive diagnostics at a frozen threshold; no model tuning."""

import math

from ml.gate_evaluation import alarms, intervals
from ml.gate_features import SAMPLE_MS
from ml.gate_residuals import timed_alarms


def _is_finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def diagnose_events(times, scores, labels, threshold):
    """Explain misses without resetting alarm state at truth boundaries."""
    if not times or any(type(value) is not int for value in times):
        raise ValueError("Diagnostics require integer timestamps.")
    if not _is_finite_number(threshold) or threshold < 0:
        raise ValueError("Diagnostics require a finite nonnegative numeric threshold.")
    if len(times) != len(labels) or len(times) != len(scores):
        raise ValueError("Diagnostics require equal numbers of timestamps, scores, and labels.")
    if any(type(value) is not bool for value in labels):
        raise ValueError("Diagnostic labels must be boolean.")
    if any(not _is_finite_number(value) or value < 0 for value in scores):
        raise ValueError("Diagnostic scores must be finite nonnegative numbers.")
    if any(now != times[0] + index * SAMPLE_MS for index, now in enumerate(times)):
        raise ValueError("Diagnostic timestamps must be contiguous on the sample grid.")
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
