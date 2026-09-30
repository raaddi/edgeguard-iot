"""Small CPU GRU: mixed sensor targets, normal-only validation selection."""

from dataclasses import asdict
import hashlib
import json

import numpy as np
import torch
from torch import nn

from ml.gate_forecast_data import FEATURE_NAMES, ForecastPreprocessor
from ml.gate_sequences import TARGET_NAMES, SEQUENCE_VERSION
from ml.gate_sequences import validate_config

MODEL_VERSION = "gate-gru-1"
BATCH_SIZE = 128


class GateGRU(nn.Module):
    def __init__(self, hidden_size=16):
        super().__init__()
        self.hidden_size = hidden_size
        self.history_samples = None
        self.gru = nn.GRU(len(FEATURE_NAMES) * 2, hidden_size, batch_first=True)
        self.output = nn.Linear(hidden_size, 3)

    def forward(self, x):
        # No hidden state is carried across windows or sessions.
        _, hidden = self.gru(x)
        return self.output(hidden[-1])


def loss(output, target, mask):
    contacts = nn.functional.binary_cross_entropy_with_logits(output[:, :2], target[:, :2])
    observed = mask[:, 2]
    current = ((output[observed, 2] - target[observed, 2]) ** 2).mean() if observed.any() else output[:, 2].sum() * 0
    return contacts + current


def _tensors(prep, x, y):
    targets, mask = prep.targets(y)
    return (torch.from_numpy(prep.transform(x)), torch.from_numpy(targets), torch.from_numpy(mask))


def validation_loss(model, tensors):
    x, y, mask = tensors
    contacts, current, observed = 0., 0., 0
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(x), BATCH_SIZE):
            output = model(x[start:start + BATCH_SIZE])
            target, valid = y[start:start + BATCH_SIZE], mask[start:start + BATCH_SIZE, 2]
            contacts += nn.functional.binary_cross_entropy_with_logits(
                output[:, :2], target[:, :2], reduction="sum").item()
            current += ((output[valid, 2] - target[valid, 2]) ** 2).sum().item()
            observed += int(valid.sum())
    return contacts / (len(x) * 2) + (current / observed if observed else 0.)


def fit_gru(prep, train_x, train_y, validation_x, validation_y, *, epochs=30, seed=42):
    if type(epochs) is not int or not 1 <= epochs <= 200:
        raise ValueError("epochs must be in 1..200.")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be in 0..2**32-1.")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(seed)
    train, validation = _tensors(prep, train_x, train_y), _tensors(prep, validation_x, validation_y)
    model = GateGRU()
    model.history_samples = train_x.shape[1]
    if validation_x.shape[1:] != train_x.shape[1:]:
        raise ValueError("Training and validation history shapes differ.")
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
    generator = torch.Generator().manual_seed(seed)
    initial = validation_loss(model, validation)
    best, best_epoch, best_weights, history = float("inf"), None, None, []
    for epoch in range(1, epochs + 1):
        model.train()
        order = torch.randperm(len(train_x), generator=generator)
        for start in range(0, len(order), BATCH_SIZE):
            indices = order[start:start + BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            value = loss(model(train[0][indices]), train[1][indices], train[2][indices])
            if not torch.isfinite(value):
                raise ValueError("Nonfinite GRU training loss.")
            value.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.)
            optimizer.step()
        score = validation_loss(model, validation)
        if not np.isfinite(score):
            raise ValueError("Nonfinite validation loss.")
        history.append({"epoch": epoch, "normal_validation_loss": score})
        if score < best:
            best, best_epoch = score, epoch
            best_weights = {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_weights)
    model.eval()
    return model, {"initial_validation_loss": initial, "best_epoch": best_epoch,
                   "best_validation_loss": best, "history": history}


def forecast(model, prep, x):
    if (x.ndim != 3 or x.shape[-1] != len(FEATURE_NAMES) or not len(x)
            or x.shape[1] != model.history_samples):
        raise ValueError("Forecast history shape differs from the fitted model.")
    inputs = torch.from_numpy(prep.transform(x))
    predictions = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(inputs), BATCH_SIZE):
            output = model(inputs[start:start + BATCH_SIZE])
            predictions.append(torch.cat((torch.sigmoid(output[:, :2]), output[:, 2:]), dim=1).numpy())
    result = np.concatenate(predictions).astype(np.float64)
    result[:, 2] = (result[:, 2] * prep.current_scale + prep.current_mean) if prep.current_enabled else np.nan
    return result


def save_forecaster(root, model, prep, sequence_config):
    weights = root / "weights.pt"
    torch.save(model.state_dict(), weights)
    config = {"model_version": MODEL_VERSION, "sequence_version": SEQUENCE_VERSION,
              "feature_names": list(FEATURE_NAMES), "target_names": list(TARGET_NAMES),
              "hidden_size": model.hidden_size, "preprocessor": asdict(prep),
              "sequence_config": sequence_config,
              "weights_sha256": hashlib.sha256(weights.read_bytes()).hexdigest()}
    (root / "model.json").write_text(json.dumps(config, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_forecaster(root):
    """Load our own local artifact; do not load arbitrary downloaded models."""
    config = json.loads((root / "model.json").read_text(encoding="utf-8"))
    if (config["model_version"] != MODEL_VERSION or config["sequence_version"] != SEQUENCE_VERSION
            or config["feature_names"] != list(FEATURE_NAMES) or config["target_names"] != list(TARGET_NAMES)
            or config["hidden_size"] != 16):
        raise ValueError("Unsupported forecast model configuration.")
    weights = root / "weights.pt"
    if hashlib.sha256(weights.read_bytes()).hexdigest() != config["weights_sha256"]:
        raise ValueError("Model weights hash mismatch.")
    model = GateGRU(config["hidden_size"])
    validate_config(config["sequence_config"]["history_samples"], config["sequence_config"]["horizon_samples"])
    model.history_samples = config["sequence_config"]["history_samples"]
    model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
    model.eval()
    return model, ForecastPreprocessor(**config["preprocessor"]), config
