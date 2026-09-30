"""Validated sequence exports and train-only preprocessing for gate forecasts."""

from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np

from ml.gate_feature_export import _decode, _read, validate_plan
from ml.gate_features import FEATURE_VERSION, SAMPLE_MS
from ml.gate_sequence_export import EXPORT_VERSION, MAX_EXAMPLES
from ml.gate_sequences import SEQUENCE_VERSION, TARGET_NAMES, validate_config

FEATURE_NAMES = tuple(sorted((
    "closed_contact", "open_contact", "current_a", "current_missing", "current_mean_a",
    "current_max_a", "current_available_fraction", "sample_coverage", "history_span_ms",
    "sample_gap_ms", "contact_transitions", "commands_in_window", "pending_commands",
    "last_command_degrees", "command_age_ms", "last_result_delay_ms", "last_result_accepted",
    "accepted_target_degrees", "accepted_target_age_ms", "target_contact_delay_ms",
)))


class SequenceDataset:
    """Read only the requested partitions; metadata never enters input tensors."""

    def __init__(self, root):
        self.root = Path(root)
        raw = _read(self.root / "manifest.json")
        self.manifest_sha256 = hashlib.sha256(raw).hexdigest()
        m = self.manifest = _decode(raw)
        split = _read(self.root / "source-split.json")
        self.plan = _decode(split)
        validate_plan(self.plan)
        if (m["status"] != "completed" or m["export_version"] != EXPORT_VERSION
                or m["sequence_version"] != SEQUENCE_VERSION or m["feature_version"] != FEATURE_VERSION
                or m["target_names"] != list(TARGET_NAMES) or m["sample_ms"] != SAMPLE_MS
                or m["aggregate_window_ms"] != 1000
                or hashlib.sha256(split).hexdigest() != m["split_sha256"]):
            raise ValueError("Unsupported or inconsistent sequence export.")
        validate_config(m["history_samples"], m["horizon_samples"])
        expected = {(p, s["run_id"]) for p in ("train", "validation", "test")
                    for s in self.plan["partitions"][p]}
        self.entries = {(s["partition"], s["run_id"]): s for s in m["sessions"]}
        if len(self.entries) != len(m["sessions"]) or set(self.entries) != expected:
            raise ValueError("Sequence sessions differ from the frozen split.")
        counts = [s["examples"] for s in m["sessions"]]
        if (any(type(n) is not int or not 0 <= n <= 10000 for n in counts)
                or sum(counts) != m["examples"] or not 1 <= sum(counts) <= MAX_EXAMPLES):
            raise ValueError("Invalid example counts.")

    def sessions(self, partition, *, normal_only=False):
        if partition not in ("train", "validation", "test"):
            raise ValueError("Invalid forecast partition.")
        sessions = sorted(self.plan["partitions"][partition],
                          key=lambda s: (s["paired_group"], s["profile"], s["case"], s["run_id"]))
        for session in sessions:
            if normal_only and session["case"] != "normal":
                continue
            entry = self.entries[partition, session["run_id"]]
            path = self.root / partition / (session["run_id"] + ".jsonl")
            with path.open("rb") as stream:
                raw = stream.read(64 * 1024 * 1024 + 1)
            if len(raw) > 64 * 1024 * 1024:
                raise ValueError("Sequence session exceeds 64 MiB; use a smaller pilot.")
            if hashlib.sha256(raw).hexdigest() != entry["sequences_sha256"]:
                raise ValueError("Sequence hash mismatch.")
            lines = raw.splitlines()
            if len(lines) != entry["examples"]:
                raise ValueError("Sequence count mismatch.")
            xs, ys, times = [], [], []
            for line in lines:
                row = _decode(line)
                x, y = self._validate_row(row)
                if times and row["target_ms"] <= times[-1]:
                    raise ValueError("Forecast timestamps must increase.")
                xs.append(x)
                ys.append(y)
                times.append(row["target_ms"])
            if not xs:
                raise ValueError("Session has no complete forecast examples.")
            yield session, np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.float32), times

    def _validate_row(self, row):
        h, horizon = self.manifest["history_samples"], self.manifest["horizon_samples"]
        if set(row) != {"x", "y", "input_times_ms", "prediction_ms", "target_ms", "persistence"}:
            raise ValueError("Unsupported forecast fields.")
        t, target = row["prediction_ms"], row["target_ms"]
        if (type(t) is not int or type(target) is not int or not 0 <= t < target <= 500000
                or target != t + SAMPLE_MS * horizon or t % SAMPLE_MS
                or t < (h - 1) * SAMPLE_MS
                or row["input_times_ms"] != list(range(t - (h - 1) * SAMPLE_MS, t + 1, SAMPLE_MS))
                or len(row["x"]) != h or set(row["y"]) != set(TARGET_NAMES)):
            raise ValueError("Invalid forecast timing/shape.")
        x = []
        for sample in row["x"]:
            if set(sample) != set(FEATURE_NAMES):
                raise ValueError("Unexpected feature schema.")
            values = [sample[k] for k in FEATURE_NAMES]
            if any(v is not None and (type(v) not in (int, float)
                       or not np.isfinite(v) or abs(v) > 1e9) for v in values):
                raise ValueError("Invalid numeric feature.")
            if any(sample[k] not in (0, 1) for k in TARGET_NAMES[:2]):
                raise ValueError("Invalid input contacts.")
            x.append([np.nan if v is None else v for v in values])
        y = row["y"]
        if any(type(y[k]) is not bool for k in TARGET_NAMES[:2]):
            raise ValueError("Invalid target contacts.")
        current = y["current_a"]
        if current is not None and (type(current) not in (int, float)
                                   or not np.isfinite(current) or not 0 <= current <= 100):
            raise ValueError("Invalid target current.")
        if row["persistence"] != {k: row["x"][-1][k] for k in TARGET_NAMES}:
            raise ValueError("Persistence reference does not match history.")
        return x, [float(y[k]) if y[k] is not None else np.nan for k in TARGET_NAMES]


def normal_arrays(dataset, partition):
    batches = list(dataset.sessions(partition, normal_only=True))
    if not batches:
        raise ValueError("Normal sessions required for fitting and selection.")
    return np.concatenate([b[1] for b in batches]), np.concatenate([b[2] for b in batches])


@dataclass
class ForecastPreprocessor:
    median: list
    mean: list
    scale: list
    current_mean: float
    current_scale: float
    current_enabled: bool

    @classmethod
    def fit(cls, x, y):
        if x.ndim != 3 or x.shape[2] != len(FEATURE_NAMES) or not len(x) or y.shape != (len(x), 3):
            raise ValueError("Expected nonempty training histories and three targets.")
        flat = x.reshape(-1, x.shape[-1]).astype(np.float64)
        median = np.array([np.median(c[~np.isnan(c)]) if np.any(~np.isnan(c)) else 0
                           for c in flat.T])
        filled = np.where(np.isnan(flat), median, flat)
        mean, scale = filled.mean(0), filled.std(0)
        scale[scale < 1e-6] = 1
        current = y[:, 2][~np.isnan(y[:, 2])].astype(np.float64)
        return cls(median.tolist(), mean.tolist(), scale.tolist(),
                   float(current.mean()) if len(current) else 0.,
                   max(float(current.std()), 1e-3) if len(current) else 1., bool(len(current)))

    def transform(self, x):
        missing = np.isnan(x)
        scaled = (np.where(missing, self.median, x) - self.mean) / self.scale
        result = np.concatenate((scaled, missing.astype(np.float32)), axis=-1).astype(np.float32)
        if not np.isfinite(result).all():
            raise ValueError("Nonfinite transformed inputs.")
        return result

    def targets(self, y):
        mask = np.isfinite(y)
        mask[:, 2] &= self.current_enabled
        result = np.where(mask, y, 0).copy()
        result[:, 2] = np.where(mask[:, 2], (y[:, 2] - self.current_mean) / self.current_scale, 0)
        return result.astype(np.float32), mask
