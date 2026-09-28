"""Causal forecast examples from a single validated offline gate session."""

from ml.gate_features import SAMPLE_MS, extract_features

SEQUENCE_VERSION = "gate-sequences-1"
TARGET_NAMES = ("closed_contact", "open_contact", "current_a")


def validate_config(history_samples, horizon_samples):
    for name, value in (("history_samples", history_samples),
                        ("horizon_samples", horizon_samples)):
        if type(value) is not int or not 1 <= value <= 200:
            raise ValueError(f"{name} must be an integer in 1..200.")


def iter_sequences(observations, events, *, history_samples=20, horizon_samples=1):
    """Yield history through t and separate sensor targets at t + horizon.

    Split whole sessions before calling. Nothing is fitted or imputed here.
    Twenty samples occupy (t - 1000 ms, t], with 950 ms between endpoints.
    Any missing sample in the history or forecast interval excludes the example.
    Causal aggregate features retain their own fixed 1000 ms history.
    """
    validate_config(history_samples, horizon_samples)
    features = extract_features(observations, events, window_ms=1000)
    times = [row["logical_ms"] for row in features]
    # Prefix gap counts make each continuity check independent of window length.
    gaps = [0]
    for previous, now in zip(times, times[1:]):
        gaps.append(gaps[-1] + (now - previous != SAMPLE_MS))
    for end in range(history_samples - 1, len(features) - horizon_samples):
        start, target = end - history_samples + 1, end + horizon_samples
        if gaps[target] != gaps[start]:
            continue
        yield {
            "input_times_ms": times[start:end + 1],
            "prediction_ms": times[end],
            "target_ms": times[target],
            "x": [dict(row["x"]) for row in features[start:end + 1]],
            "y": {name: observations[target][name] for name in TARGET_NAMES},
        }
