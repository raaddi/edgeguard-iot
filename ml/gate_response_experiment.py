"""Train frozen response/sensor GRUs and report forecast quality, without alarms."""

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
import torch

from ml.gate_forecast_data import ForecastPreprocessor
from ml.gate_forecast_metrics import forecast_metrics, persistence
from ml.gate_gru import fit_gru, forecast, load_forecaster, save_forecaster
from ml.gate_response_data import ResponseDataset, response_arrays, sensor_arrays
from ml.gate_response_gru import (MedianResponseBaseline, fit_response_gru,
    forecast_response, load_response_forecaster, save_response_forecaster)
from ml.gate_sequences import iter_sequences
from simulator.__main__ import code_version

EXPERIMENT_VERSION = "gate-response-forecast-comparison-1"
TRAINING_SEEDS = (7, 42, 73)
PROTOCOL_PATH = Path(__file__).resolve().parents[1] / "docs/step-20-response-models.md"
SEQUENCE_CONFIG = {"history_samples": 20, "horizon_samples": 1, "aggregate_window_ms": 1000}


def _save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def response_metrics(target, prediction, examples):
    """Only observed durations have regression errors; censoring stays separate."""
    if target.shape != prediction.shape or target.shape != (len(examples), 2):
        raise ValueError("Response metric shapes differ.")
    if not np.isfinite(prediction).all() or np.any(prediction < 0):
        raise ValueError("Response predictions must be finite and nonnegative.")
    result = {}
    for index, name in enumerate(("ack", "contact")):
        valid = np.isfinite(target[:, index])
        error = prediction[valid, index] - target[valid, index]
        reasons = Counter(row["y"][name]["censor_reason"] for row in examples
                          if not row["y"][name]["observed"])
        result[name] = {
            "examples": len(examples), "observed": int(valid.sum()),
            "censored": int((~valid).sum()), "censor_reasons": dict(sorted(reasons.items())),
            "mae_ms": float(np.abs(error).mean()) if len(error) else None,
            "rmse_ms": float(np.sqrt((error ** 2).mean())) if len(error) else None,
            "bias_ms": float(error.mean()) if len(error) else None,
        }
    return result


def _summary(rows):
    rx = np.concatenate([row["response_target"] for row in rows])
    examples = [example for row in rows for example in row["examples"]]
    sy = np.concatenate([row["sensor_target"] for row in rows])
    reference = np.concatenate([row["persistence"] for row in rows])
    response = {name: response_metrics(rx, np.concatenate([row["response"][name] for row in rows]), examples)
                for name in rows[0]["response"]}
    sensor = {name: forecast_metrics(sy, np.concatenate([row["sensor"][name] for row in rows]), reference)
              for name in rows[0]["sensor"]}
    spread = {}
    for channel in ("ack", "contact"):
        values = [metrics[channel]["mae_ms"] for name, metrics in response.items()
                  if name.startswith("gru_") and metrics[channel]["mae_ms"] is not None]
        spread[channel] = {"minimum_mae_ms": min(values) if values else None,
                           "median_mae_ms": float(np.median(values)) if values else None,
                           "maximum_mae_ms": max(values) if values else None}
    return {"sessions": len(rows), "response_examples": len(rx), "sensor_examples": len(sy),
            "response": response, "sensor": sensor, "response_seed_spread": spread}


def _grouped(rows, key):
    return {value: _summary([row for row in rows if row["entry"][key] == value])
            for value in sorted({row["entry"][key] for row in rows})}


def _numbers(values):
    return [float(value) if np.isfinite(value) else None for value in values]


def run_experiment(source, output, *, epochs=30):
    if type(epochs) is not int or not 1 <= epochs <= 200:
        raise ValueError("epochs must be in 1..200.")
    if (not TRAINING_SEEDS or len(set(TRAINING_SEEDS)) != len(TRAINING_SEEDS)
            or any(type(seed) is not int or not 0 <= seed < 2**32 for seed in TRAINING_SEEDS)):
        raise ValueError("Training seeds must be unique bounded integers.")
    dataset = ResponseDataset(source)
    protocol = PROTOCOL_PATH.read_bytes()
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    metadata = {
        "status": "running", "experiment_version": EXPERIMENT_VERSION,
        "code_version": code_version(), "source_manifest_sha256": dataset.manifest_sha256,
        "training_seeds": list(TRAINING_SEEDS), "epochs": epochs,
        "protocol_sha256": hashlib.sha256(protocol).hexdigest(),
        "versions": {"python": platform.python_version(), "torch": str(torch.__version__),
                     "numpy": np.__version__},
        "architecture": {"hidden_size": 16, "layers": 1, "bidirectional": False,
                         "input_channels": 40, "history_samples": 20},
        "training": {"device": "cpu", "threads": 1, "batch_size": 128, "optimizer": "Adam",
                     "learning_rate": .003, "gradient_clip_norm": 1.,
                     "selection": "minimum normal selection loss; earliest epoch on ties",
                     "shared_preprocessing": "normal train sensor histories only",
                     "response_loss": "channel-balanced observed log1p(ms/50) MSE",
                     "sensor_loss": "contact BCE + masked standardized-current MSE"},
        "limitations": ["synthetic development forecast study, not alarm evaluation",
                        "response and sensor heads have different targets and sample counts",
                        "censored responses have no MAE target and are not fault labels",
                        "calibration and evaluation are never used for fitting or selection",
                        "all declared training seeds reported, no winning seed selection",
                        "no live Qt/MQTT, physical transfer or Raspberry Pi measurements"],
        "models": [], "prediction_files": [],
    }
    _save(root / "manifest.json", metadata)
    try:
        (root / "protocol.md").write_bytes(protocol)
        (root / "source-manifest.json").write_bytes((Path(source) / "manifest.json").read_bytes())
        if digest(root / "source-manifest.json") != dataset.manifest_sha256:
            raise ValueError("Source manifest changed after validation.")
        train = list(dataset.sessions("train"))
        selection = list(dataset.sessions("selection"))
        tx, ty, _ = response_arrays(train)
        vx, vy, _ = response_arrays(selection)
        sx, sy = sensor_arrays(train)
        svx, svy = sensor_arrays(selection)
        prep = ForecastPreprocessor.fit(sx, sy)
        _save(root / "preprocessing.json", asdict(prep))
        baseline = MedianResponseBaseline.fit(tx, ty)
        _save(root / "baseline.json", baseline.to_config())
        restored_baseline = MedianResponseBaseline.from_config(json.loads((root / "baseline.json").read_text(encoding="utf-8")))
        np.testing.assert_array_equal(baseline.predict(vx), restored_baseline.predict(vx))
        baseline = restored_baseline
        models, training = {}, {}
        for seed in TRAINING_SEEDS:
            print(f"Training response GRU, seed {seed}...", flush=True)
            started = time.perf_counter()
            response, response_history = fit_response_gru(prep, tx, ty, vx, vy, epochs=epochs, seed=seed)
            response_history.update(training_seconds_workstation=time.perf_counter() - started,
                                    training_examples=len(tx), selection_examples=len(vx),
                                    parameters=sum(p.numel() for p in response.parameters()))
            response_root = root / "models" / f"response-{seed}"
            response_root.mkdir(parents=True)
            save_response_forecaster(response_root, response, prep)
            restored, restored_prep, _ = load_response_forecaster(response_root)
            assert asdict(restored_prep) == asdict(prep)
            np.testing.assert_array_equal(forecast_response(response, prep, vx), forecast_response(restored, restored_prep, vx))
            response = restored
            print(f"Training sensor GRU, seed {seed}...", flush=True)
            started = time.perf_counter()
            sensor, sensor_history = fit_gru(prep, sx, sy, svx, svy, epochs=epochs, seed=seed)
            sensor_history.update(training_seconds_workstation=time.perf_counter() - started,
                                  training_examples=len(sx), selection_examples=len(svx),
                                  parameters=sum(p.numel() for p in sensor.parameters()))
            sensor_root = root / "models" / f"sensor-{seed}"
            sensor_root.mkdir(parents=True)
            save_forecaster(sensor_root, sensor, prep, SEQUENCE_CONFIG)
            restored, restored_prep, _ = load_forecaster(sensor_root)
            assert asdict(restored_prep) == asdict(prep)
            np.testing.assert_array_equal(forecast(sensor, prep, svx), forecast(restored, restored_prep, svx))
            models[seed] = (response, restored)
            training[str(seed)] = {"response": response_history, "sensor": sensor_history}
            for kind, folder in (("response", response_root), ("sensor", sensor_root)):
                metadata["models"].append({"kind": kind, "seed": seed,
                    "path": folder.relative_to(root).as_posix(),
                    "model_sha256": digest(folder / "model.json"),
                    "weights_sha256": digest(folder / "weights.pt")})
        _save(root / "training.json", training)
        frozen = {"models": metadata["models"], "baseline_sha256": digest(root / "baseline.json"),
                  "preprocessing_sha256": digest(root / "preprocessing.json"),
                  "training_sha256": digest(root / "training.json")}
        _save(root / "frozen.json", frozen)
        metadata["frozen_sha256"] = digest(root / "frozen.json")
        _save(root / "manifest.json", metadata)
        del train, selection, tx, ty, vx, vy, sx, sy, svx, svy
        report = {"training": training, "roles": {}}
        for role in ("selection", "calibration", "evaluation"):
            print(f"Evaluating forecasts: {role}...", flush=True)
            rows = []
            folder = root / "predictions" / role
            folder.mkdir(parents=True)
            for session in dataset.sessions(role):
                entry, observations, events, data = session
                x, target, _ = response_arrays([session])
                sensor_x, sensor_target = sensor_arrays([session])
                response_predictions = {"median": baseline.predict(x) if len(x) else np.empty((0, 2))}
                sensor_predictions = {"persistence": persistence(sensor_x)}
                for seed, (response, sensor) in models.items():
                    response_predictions[f"gru_{seed}"] = forecast_response(response, prep, x) if len(x) else np.empty((0, 2))
                    predicted = forecast(sensor, prep, sensor_x)
                    if (not np.isfinite(predicted[:, :2]).all()
                            or prep.current_enabled and not np.isfinite(predicted).all()):
                        raise ValueError("Nonfinite sensor forecasts.")
                    sensor_predictions[f"gru_{seed}"] = predicted
                response_file = folder / (entry["run_id"] + "-response.json")
                _save(response_file, [{"command_id": example["command_id"],
                    "prediction_ms": example["prediction_ms"], "target_degrees": example["target_degrees"],
                    "actual": example["y"],
                    "predicted_ms": {name: _numbers(values[index]) for name, values in response_predictions.items()}}
                    for index, example in enumerate(data["examples"])])
                sensor_file = folder / (entry["run_id"] + "-sensor.jsonl")
                with sensor_file.open("x", encoding="utf-8") as stream:
                    for index, example in enumerate(iter_sequences(observations, events)):
                        stream.write(json.dumps({"prediction_ms": example["prediction_ms"],
                            "target_ms": example["target_ms"], "actual": _numbers(sensor_target[index]),
                            "predictions": {name: _numbers(values[index]) for name, values in sensor_predictions.items()}},
                            allow_nan=False) + "\n")
                metadata["prediction_files"].append({"run_id": entry["run_id"], "role": role,
                    "response_file": response_file.relative_to(root).as_posix(),
                    "response_sha256": digest(response_file),
                    "sensor_file": sensor_file.relative_to(root).as_posix(), "sensor_sha256": digest(sensor_file)})
                rows.append({"entry": entry, "examples": data["examples"], "response_target": target,
                             "response": response_predictions, "sensor_target": sensor_target,
                             "sensor": sensor_predictions, "persistence": sensor_predictions["persistence"]})
            report["roles"][role] = {"overall": _summary(rows), "by_case": _grouped(rows, "case"),
                "by_condition": _grouped(rows, "condition"), "by_seed": _grouped(rows, "seed"),
                "normal_by_condition": _grouped([row for row in rows if row["entry"]["case"] == "normal"], "condition"),
                "sessions": [{"run_id": row["entry"]["run_id"], "seed": row["entry"]["seed"],
                    "case": row["entry"]["case"], "condition": row["entry"]["condition"], **_summary([row])} for row in rows]}
        # The fitted artifacts must remain identical throughout calibration/evaluation.
        for entry in metadata["models"]:
            folder = root / entry["path"]
            assert digest(folder / "model.json") == entry["model_sha256"]
            assert digest(folder / "weights.pt") == entry["weights_sha256"]
        for name in ("baseline", "preprocessing", "training"):
            assert digest(root / (name + ".json")) == frozen[name + "_sha256"]
        _save(root / "report.json", report)
        metadata.update(status="completed", report_sha256=digest(root / "report.json"))
    except BaseException:
        metadata["status"] = "failed"
        raise
    finally:
        _save(root / "manifest.json", metadata)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=30)
    args = parser.parse_args()
    try:
        run_experiment(args.source, args.output, epochs=args.epochs)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, AssertionError) as error:
        parser.exit(1, f"Response forecast experiment failed: {error}\n")
    print(f"Forecast study completed: {args.output}; no anomaly alarm evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
