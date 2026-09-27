"""Train-only preprocessing and two baselines sharing the same gate features."""

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer


@dataclass
class GateDetectors:
    feature_names: tuple
    imputer: SimpleImputer
    forest: IsolationForest
    rule_limits: dict

    def matrix(self, rows):
        if not rows or any(set(row) != set(self.feature_names) for row in rows):
            raise ValueError("Expected nonempty rows with the trained feature schema.")
        matrix = np.array([[np.nan if row[k] is None else row[k] for k in self.feature_names]
                           for row in rows], dtype=float)
        if np.isinf(matrix).any():
            raise ValueError("Infinite features are not supported.")
        return matrix

    @classmethod
    def fit(cls, normal_training_rows, *, seed=42):
        if len(normal_training_rows) < 100:
            raise ValueError("At least 100 normal training rows required for this pilot.")
        model = cls(tuple(sorted(normal_training_rows[0])),
                    SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True),
                    IsolationForest(n_estimators=100, max_samples=min(256, len(normal_training_rows)), random_state=seed,
                                    contamination="auto", n_jobs=1), {})
        matrix = model.imputer.fit_transform(model.matrix(normal_training_rows))
        model.forest.fit(matrix)
        for name in ("current_a", "last_result_delay_ms", "target_contact_delay_ms"):
            values = [row[name] for row in normal_training_rows if row[name] is not None]
            if not values or max(values) <= 0:
                raise ValueError("Training needs current measurements and completed normal cycles.")
            model.rule_limits[name] = max(values)
        return model

    def scores(self, rows):
        matrix = self.imputer.transform(self.matrix(rows))
        # sklearn score_samples is smaller for anomalies; invert it once here.
        learned = (-self.forest.score_samples(matrix)).tolist()
        rules = []
        for row in rows:
            current = row["current_a"] or 0
            waiting = (row["command_age_ms"] or 0) if row["pending_commands"] else 0
            travel = ((row["accepted_target_age_ms"] or 0)
                      if row["target_contact_delay_ms"] is None else 0)
            rules.append(max(current / self.rule_limits["current_a"],
                             waiting / self.rule_limits["last_result_delay_ms"],
                             travel / self.rule_limits["target_contact_delay_ms"]))
        return {"isolation_forest": learned, "temporal_rules": rules}


def calibrate(normal_validation_scores):
    """Freeze threshold at max normal validation score; comparison uses >.

    Both methods target zero observed validation false alarms. This small-sample
    calibration provides no guarantee on future false alarm rates.
    """
    if not normal_validation_scores or not all(np.isfinite(normal_validation_scores)):
        raise ValueError("Finite normal validation scores are required.")
    return max(normal_validation_scores)
