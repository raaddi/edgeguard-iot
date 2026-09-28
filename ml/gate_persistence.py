"""Untrained next-reading reference; forecast errors are not anomaly alarms."""

import math

from ml.gate_sequences import TARGET_NAMES


def predict(history):
    """Use only input history, never the future target or the scenario label."""
    if not history:
        raise ValueError("Persistence requires at least one input sample.")
    return {name: history[-1][name] for name in TARGET_NAMES}


class PersistenceMetrics:
    """Streaming, per-channel metrics. Missing values are excluded and counted."""

    def __init__(self):
        self.examples = 0
        self.channels = {name: dict(pairs=0, missing_target=0, missing_prediction=0,
                                    absolute_error=0.0, squared_error=0.0,
                                    changes=0, unchanged=0)
                         for name in TARGET_NAMES}

    def add(self, prediction, target):
        self.examples += 1
        for name, counts in self.channels.items():
            observed, estimated = target[name], prediction[name]
            counts["missing_target"] += observed is None
            counts["missing_prediction"] += estimated is None
            if observed is None or estimated is None:
                continue
            error = abs(observed - estimated)
            counts["pairs"] += 1
            counts["absolute_error"] += error
            counts["squared_error"] += error * error
            counts["changes"] += observed != estimated
            counts["unchanged"] += observed == estimated

    def report(self):
        result = {}
        for name, c in self.channels.items():
            pairs = c["pairs"]
            counts = {k: c[k] for k in ("pairs", "missing_target", "missing_prediction")}
            if name == "current_a":
                counts.update(mae_a=c["absolute_error"] / pairs if pairs else None,
                              rmse_a=math.sqrt(c["squared_error"] / pairs) if pairs else None)
            else:
                # For this reference every change since the last input is an error.
                counts.update(errors=c["changes"], target_changes=c["changes"],
                              unchanged_pairs=c["unchanged"],
                              error_rate=c["changes"] / pairs if pairs else None)
            result[name] = counts
        return {"examples": self.examples, "channels": result}
