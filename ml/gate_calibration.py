"""Session-local normal calibration for three-sample causal alarms."""

import math


def calibrate_sessions(sessions):
    """Two frozen policies target zero observed calibration alarm starts.

    A three-sample alarm needs the minimum of its three scores to exceed the
    threshold. Taking the maximum of these minima protects every calibration
    triple without letting an isolated spike set the threshold. Sessions never
    share triples. This provides no guarantee on future false alarm rates.
    """
    peaks, sustained = [], []
    for scores in sessions:
        if len(scores) < 3 or any(v is None or not math.isfinite(v) for v in scores):
            raise ValueError("Each calibration session needs at least three finite scores.")
        peaks.append(max(scores))
        sustained.extend(min(scores[i:i + 3]) for i in range(len(scores) - 2))
    if not peaks:
        raise ValueError("Normal calibration sessions required.")
    return {"sample_max": max(peaks), "sustained_max": max(sustained)}
