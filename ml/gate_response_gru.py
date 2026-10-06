"""CPU forecasts of command ACK and physical contact latency.

Both durations are predictions made from histories ending at command send.
Unfinished outcomes are masked, never converted to zero-duration targets.
"""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import torch
from torch import nn

from ml.gate_features import FEATURE_VERSION, SAMPLE_MS
from ml.gate_forecast_data import FEATURE_NAMES, ForecastPreprocessor
from ml.gate_response_targets import RESPONSE_VERSION

MODEL_VERSION = "gate-response-gru-1"
BASELINE_VERSION = "gate-response-median-1"
RESPONSE_TARGET_NAMES = ("ack", "contact")
TARGET_TRANSFORM = "log1p(duration_ms/50)"
BATCH_SIZE = 128


def _history(value):
    if type(value) is not int or not 1 <= value <= 200:
        raise ValueError("history_samples must be an integer in 1..200.")
    return value


def _inputs(x, *, history_samples=None):
    try:
        x = np.asarray(x, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid numeric response histories.") from error
    if (x.ndim != 3 or not len(x) or x.shape[2] != len(FEATURE_NAMES)
            or not 1 <= x.shape[1] <= 200
            or history_samples is not None and x.shape[1] != history_samples):
        raise ValueError("Response history shape differs from the fitted model.")
    if np.isinf(x).any() or np.any(np.abs(x[~np.isnan(x)]) > 1e9):
        raise ValueError("Nonfinite or out-of-range response inputs.")
    return x


def _targets(y, count, *, require_observed=True):
    try:
        y = np.asarray(y, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError("Invalid numeric response targets.") from error
    if y.shape != (count, 2) or np.isinf(y).any() or np.any(y[~np.isnan(y)] < 0):
        raise ValueError("Expected nonnegative ACK/contact targets; censored values must be NaN.")
    mask = ~np.isnan(y)
    if require_observed and not mask.any(axis=0).all():
        raise ValueError("Both response targets need observed durations.")
    return y, mask


def _preprocessor(prep):
    if not isinstance(prep, ForecastPreprocessor):
        raise ValueError("Expected the shared forecast preprocessor.")
    for name in ("median", "mean", "scale"):
        values = getattr(prep, name)
        if (not isinstance(values, list) or len(values) != len(FEATURE_NAMES)
                or any(type(v) not in (int, float) or not np.isfinite(v) for v in values)):
            raise ValueError("Invalid response preprocessor parameters.")
    if (any(v <= 0 for v in prep.scale)
            or type(prep.current_enabled) is not bool
            or type(prep.current_mean) not in (int, float) or not np.isfinite(prep.current_mean)
            or type(prep.current_scale) not in (int, float)
            or not np.isfinite(prep.current_scale) or prep.current_scale <= 0):
        raise ValueError("Invalid response preprocessor scales.")
    return prep


class ResponseGRU(nn.Module):
    """One unidirectional layer and a nonnegative two-duration log head."""

    def __init__(self):
        super().__init__()
        self.hidden_size = 16
        self.history_samples = None
        self.gru = nn.GRU(len(FEATURE_NAMES) * 2, 16, batch_first=True)
        self.output = nn.Linear(16, 2)

    def forward(self, x):
        _, hidden = self.gru(x)
        return nn.functional.softplus(self.output(hidden[-1]))


def response_loss(output, target, mask):
    """Mean observed log error per channel, then mean available channels.

    Index before subtraction: NaN values at censored positions never enter
    arithmetic or gradients. A wholly censored batch has a zero empty sum.
    """
    values = [((output[mask[:, channel], channel] - target[mask[:, channel], channel]) ** 2).mean()
              for channel in range(2) if mask[:, channel].any()]
    return torch.stack(values).mean() if values else output[mask].sum()


masked_loss = response_loss


def _tensors(prep, x, y):
    target, mask = _targets(y, len(x))
    transformed = np.log1p(target / SAMPLE_MS).astype(np.float32)
    return (torch.from_numpy(prep.transform(x)), torch.from_numpy(transformed), torch.from_numpy(mask))


def selection_loss(model, tensors):
    x, y, mask = tensors
    sums, counts = np.zeros(2, dtype=np.float64), np.zeros(2, dtype=np.int64)
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(x), BATCH_SIZE):
            output = model(x[start:start + BATCH_SIZE])
            target, valid = y[start:start + BATCH_SIZE], mask[start:start + BATCH_SIZE]
            for channel in range(2):
                selected = valid[:, channel]
                sums[channel] += ((output[selected, channel] - target[selected, channel]) ** 2).sum().item()
                counts[channel] += int(selected.sum())
    if not counts.all():
        raise ValueError("Both selection targets need observed durations.")
    return float(np.mean(sums / counts))


def fit_response_gru(prep, train_x, train_y, selection_x, selection_y, *, epochs=30, seed=42):
    if type(epochs) is not int or not 1 <= epochs <= 200:
        raise ValueError("epochs must be in 1..200.")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be in 0..2**32-1.")
    _preprocessor(prep)
    train_x = _inputs(train_x)
    selection_x = _inputs(selection_x, history_samples=train_x.shape[1])
    train, selection = _tensors(prep, train_x, train_y), _tensors(prep, selection_x, selection_y)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(seed)
    model = ResponseGRU()
    model.history_samples = train_x.shape[1]
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
    generator = torch.Generator().manual_seed(seed)
    initial = selection_loss(model, selection)
    best, best_epoch, best_weights, history = float("inf"), None, None, []
    for epoch in range(1, epochs + 1):
        model.train()
        order = torch.randperm(len(train_x), generator=generator)
        for start in range(0, len(order), BATCH_SIZE):
            indices = order[start:start + BATCH_SIZE]
            if not train[2][indices].any():
                continue
            optimizer.zero_grad(set_to_none=True)
            value = response_loss(model(train[0][indices]), train[1][indices], train[2][indices])
            if not torch.isfinite(value):
                raise ValueError("Nonfinite response training loss.")
            value.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.)
            optimizer.step()
        score = selection_loss(model, selection)
        if not np.isfinite(score):
            raise ValueError("Nonfinite response selection loss.")
        history.append({"epoch": epoch, "normal_selection_loss": score})
        if score < best:
            best, best_epoch = score, epoch
            best_weights = {key: value.detach().clone() for key, value in model.state_dict().items()}
    model.load_state_dict(best_weights)
    model.eval()
    return model, {"initial_selection_loss": initial, "best_epoch": best_epoch,
                   "best_selection_loss": best, "history": history}


def forecast_response(model, prep, x):
    _preprocessor(prep)
    _history(model.history_samples)
    inputs = torch.from_numpy(prep.transform(_inputs(x, history_samples=model.history_samples)))
    predictions = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(inputs), BATCH_SIZE):
            output = model(inputs[start:start + BATCH_SIZE]).numpy().astype(np.float64)
            with np.errstate(over="ignore", invalid="ignore"):
                predictions.append(SAMPLE_MS * np.expm1(output))
    result = np.concatenate(predictions)
    if result.shape != (len(inputs), 2) or not np.isfinite(result).all() or (result < 0).any():
        raise ValueError("Nonfinite or negative response forecasts.")
    return result


def save_response_forecaster(root, model, prep):
    root = Path(root)
    _preprocessor(prep)
    _history(model.history_samples)
    if not isinstance(model, ResponseGRU) or model.hidden_size != 16:
        raise ValueError("Unsupported response model architecture.")
    if any(not torch.isfinite(value).all() for value in model.state_dict().values()):
        raise ValueError("Nonfinite response model weights.")
    root.mkdir(parents=True, exist_ok=True)
    weights = root / "weights.pt"
    torch.save(model.state_dict(), weights)
    config = {"model_version": MODEL_VERSION, "response_version": RESPONSE_VERSION,
              "feature_version": FEATURE_VERSION, "feature_names": list(FEATURE_NAMES),
              "target_names": list(RESPONSE_TARGET_NAMES), "target_transform": TARGET_TRANSFORM,
              "sample_ms": SAMPLE_MS, "history_samples": model.history_samples,
              "hidden_size": 16, "layers": 1, "bidirectional": False,
              "preprocessor": asdict(prep),
              "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest()}
    (root / "model.json").write_text(json.dumps(config, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_response_forecaster(root):
    """Load the project's local hashed weights using torch's restricted reader."""
    root = Path(root)
    try:
        config = json.loads((root / "model.json").read_text(encoding="utf-8"))
        fixed = {"model_version": MODEL_VERSION, "response_version": RESPONSE_VERSION,
                 "feature_version": FEATURE_VERSION, "feature_names": list(FEATURE_NAMES),
                 "target_names": list(RESPONSE_TARGET_NAMES), "target_transform": TARGET_TRANSFORM,
                 "sample_ms": SAMPLE_MS, "hidden_size": 16, "layers": 1, "bidirectional": False}
        expected = set(fixed) | {"history_samples", "preprocessor", "weights_sha256"}
        if (not isinstance(config, dict) or set(config) != expected
                or any(config[key] != value for key, value in fixed.items())
                or any(type(config[key]) is not int for key in ("sample_ms", "hidden_size", "layers"))
                or type(config["bidirectional"]) is not bool):
            raise ValueError("Unsupported response model configuration.")
        _history(config["history_samples"])
        prep = _preprocessor(ForecastPreprocessor(**config["preprocessor"]))
        if not isinstance(config["weights_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", config["weights_sha256"]):
            raise ValueError("Invalid response weights hash.")
    except (KeyError, TypeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Invalid response model configuration.") from error
    weights = root / "weights.pt"
    if hashlib.sha256(weights.read_bytes()).hexdigest() != config["weights_sha256"]:
        raise ValueError("Response model weights hash mismatch.")
    model = ResponseGRU()
    model.history_samples = config["history_samples"]
    try:
        state = torch.load(weights, map_location="cpu", weights_only=True)
        if not isinstance(state, dict) or any(not isinstance(value, torch.Tensor) or not torch.isfinite(value).all()
                                               for value in state.values()):
            raise ValueError("Invalid response weights.")
        model.load_state_dict(state)
    except (RuntimeError, TypeError, KeyError) as error:
        raise ValueError("Invalid response weights.") from error
    model.eval()
    return model, prep, config


def _group_keys(x):
    targets = x[:, -1, FEATURE_NAMES.index("last_command_degrees")]
    closed = x[:, -1, FEATURE_NAMES.index("closed_contact")]
    opened = x[:, -1, FEATURE_NAMES.index("open_contact")]
    if (not np.isin(targets, (0, 110)).all() or not np.isin(closed, (0, 1)).all()
            or not np.isin(opened, (0, 1)).all()):
        raise ValueError("Baseline needs a known command and contact state at send.")
    return [(str(int(target)), str(int(open_contact if target == 110 else closed_contact)))
            for target, closed_contact, open_contact in zip(targets, closed, opened)]


def _medians(y):
    return [float(np.median(column[~np.isnan(column)])) if (~np.isnan(column)).any() else None for column in y.T]


class MedianResponseBaseline:
    """Train-only median by commanded target and already-achieved contact state."""

    def __init__(self, history_samples, groups, targets, global_medians):
        self.history_samples = history_samples
        self.groups = groups
        self.targets = targets
        self.global_medians = global_medians

    @classmethod
    def fit(cls, train_x, train_y):
        x = _inputs(train_x)
        y, _ = _targets(train_y, len(x))
        keys = _group_keys(x)
        groups = {f"{target}:{reached}": _medians(y[[key == (target, reached) for key in keys]])
                  for target, reached in sorted(set(keys))}
        targets = {target: _medians(y[[key[0] == target for key in keys]]) for target in sorted({key[0] for key in keys})}
        return cls(x.shape[1], groups, targets, _medians(y))

    def predict(self, x):
        x = _inputs(x, history_samples=_history(self.history_samples))
        values = []
        for target, reached in _group_keys(x):
            group = self.groups.get(f"{target}:{reached}", [None, None])
            target_medians = self.targets.get(target, [None, None])
            values.append([group[channel] if group[channel] is not None else
                           target_medians[channel] if target_medians[channel] is not None else
                           self.global_medians[channel] for channel in range(2)])
        return np.asarray(values, dtype=np.float64)

    def to_config(self):
        return {"baseline_version": BASELINE_VERSION, "feature_names": list(FEATURE_NAMES),
                "target_names": list(RESPONSE_TARGET_NAMES), "history_samples": self.history_samples,
                "groups": {key: list(value) for key, value in self.groups.items()},
                "targets": {key: list(value) for key, value in self.targets.items()},
                "global_medians": list(self.global_medians)}

    @classmethod
    def from_config(cls, config):
        try:
            if (not isinstance(config, dict) or set(config) != {"baseline_version", "feature_names", "target_names",
                        "history_samples", "groups", "targets", "global_medians"}
                    or config["baseline_version"] != BASELINE_VERSION
                    or config["feature_names"] != list(FEATURE_NAMES)
                    or config["target_names"] != list(RESPONSE_TARGET_NAMES)):
                raise ValueError("Unsupported response baseline configuration.")
            history = _history(config["history_samples"])
            groups, targets, global_values = config["groups"], config["targets"], config["global_medians"]
            if (not isinstance(groups, dict) or not groups or not isinstance(targets, dict) or not targets
                    or not set(groups) <= {"0:0", "0:1", "110:0", "110:1"}
                    or not set(targets) <= {"0", "110"}
                    or {key.split(":")[0] for key in groups} != set(targets)):
                raise ValueError("Invalid response baseline groups.")
            for values in [*groups.values(), *targets.values(), global_values]:
                if (not isinstance(values, list) or len(values) != 2
                        or any(value is not None and (type(value) not in (int, float)
                                 or not np.isfinite(value) or value < 0) for value in values)):
                    raise ValueError("Invalid response baseline medians.")
            if any(value is None for value in global_values):
                raise ValueError("Response baseline requires both global medians.")
            return cls(history, {key: list(value) for key, value in groups.items()},
                       {key: list(value) for key, value in targets.items()}, list(global_values))
        except (KeyError, TypeError) as error:
            raise ValueError("Invalid response baseline configuration.") from error
