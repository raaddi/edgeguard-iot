"""Forecast quality, separately from anomaly event detection."""

import numpy as np

from ml.gate_forecast_data import FEATURE_NAMES
from ml.gate_sequences import TARGET_NAMES


def persistence(x):
    return x[:, -1, [FEATURE_NAMES.index(k) for k in TARGET_NAMES]].astype(np.float64)


def forecast_metrics(target, prediction, last):
    """Compare methods on targets whose last input is also available.

    Contact change means target differs from the last input, never a fault label.
    Continuous errors stay in amperes; probabilities use Brier score.
    """
    report = {}
    for i, name in enumerate(TARGET_NAMES):
        eligible = np.isfinite(target[:, i]) & np.isfinite(last[:, i])
        valid = eligible & np.isfinite(prediction[:, i])
        actual, estimated = target[valid, i], prediction[valid, i]
        row = {"eligible_pairs": int(eligible.sum()), "pairs": int(valid.sum()),
               "unavailable_pairs": int(len(target) - valid.sum()),
               "missing_predictions_on_eligible": int((eligible & ~valid).sum())}
        if i == 2:
            error = estimated - actual
            row.update(mae_a=float(np.abs(error).mean()) if len(error) else None,
                       rmse_a=float(np.sqrt((error ** 2).mean())) if len(error) else None)
        else:
            errors = (estimated >= .5) != actual
            changes = actual != last[valid, i]
            row.update(errors=int(errors.sum()), error_rate=float(errors.mean()) if len(errors) else None,
                       brier=float(((estimated - actual) ** 2).mean()) if len(actual) else None,
                       changed_pairs=int(changes.sum()), changed_errors=int(errors[changes].sum()),
                       unchanged_pairs=int((~changes).sum()), unchanged_errors=int(errors[~changes].sum()))
        report[name] = row
    return report
