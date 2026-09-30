"""Train a CPU GRU on normal sessions, then compare forecasts with persistence."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
import torch

from ml.gate_forecast_data import ForecastPreprocessor, SequenceDataset, normal_arrays
from ml.gate_forecast_metrics import forecast_metrics, persistence
from ml.gate_gru import MODEL_VERSION, fit_gru, forecast, load_forecaster, save_forecaster
from ml.gate_sequence_export import _save
from simulator.__main__ import code_version


def _numbers(values):
    return [float(v) if np.isfinite(v) else None for v in values]


def _write_report(path, report):
    lines = ["# Pierwszy pilot GRU — przewidywanie odczytów", "",
             "Dane syntetyczne. To ocena prognoz, nie skuteczności alarmów.",
             "Wcześniej oglądany test pilota jest zbiorem rozwojowym, nie końcowym testem pracy.", "",
             "Wyniki poniżej dotyczą poprawnych sesji (normal). Pełny podział przypadków: report.json.", "",
             "| Podział | Metoda | MAE prądu [A] | Błędy krańcówki zamkniętej | Błędy krańcówki otwartej |",
             "|---|---|---:|---:|---:|"]
    for partition, result in report["partitions"].items():
        for method, channels in result["by_case"]["normal"].items():
            current = channels["current_a"]["mae_a"]
            text = f"{current:.6f}" if current is not None else "brak par"
            closed, opened = channels["closed_contact"], channels["open_contact"]
            lines.append(f"| {partition} | {method} | {text} | {closed['errors']}/{closed['pairs']} | "
                         f"{opened['errors']}/{opened['pairs']} |")
    lines.extend(["", "Raport JSON rozdziela błędy przy zmianie krańcówki i bez zmiany.",
                  "Duży udział bezruchu może zawyżać średnią trafność. Brier ocenia prawdopodobieństwa.",
                  "Brak pomiaru nie oznacza zera. Błędy prądu i krańcówek mają osobne jednostki.",
                  "Wagi wybieramy według straty na normalnej walidacji, przed odczytem testu.",
                  "Brak progów alarmowych, oceny zdarzeń, integracji Qt i walidacji sprzętowej.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def run_experiment(sequences, output, *, epochs=30, seed=42):
    if type(epochs) is not int or not 1 <= epochs <= 200 or type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("Use 1..200 epochs and a seed in 0..2**32-1.")
    dataset = SequenceDataset(sequences)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    config = {k: dataset.manifest[k] for k in ("history_samples", "horizon_samples", "aggregate_window_ms")}
    metadata = {
        "status": "running", "experiment_version": "gate-gru-forecast-1", "model_version": MODEL_VERSION,
        "code_version": code_version(), "source_manifest_sha256": dataset.manifest_sha256,
        "sequence_config": config, "seed": seed, "epochs": epochs,
        "versions": {"python": platform.python_version(), "torch": str(torch.__version__), "numpy": np.__version__},
        "architecture": {"hidden_size": 16, "layers": 1, "bidirectional": False, "input_size": 40, "outputs": 3},
        "training": {"device": "cpu", "threads": 1, "batch_size": 128, "optimizer": "Adam",
                     "learning_rate": .003, "gradient_clip_norm": 1., "deterministic_algorithms": True,
                     "loss": "mean contact BCE + mean masked standardized-current MSE",
                     "selection": "minimum normal-validation loss; earliest epoch on ties"},
        "limitations": ["synthetic same-family development pilot", "overlapping windows are not independent",
                        "no final held-out evaluation", "forecast errors are not anomaly alarms",
                        "no Qt, physical transfer or Raspberry Pi runtime validation"],
    }
    _save(root / "manifest.json", metadata)
    try:
        (root / "source-manifest.json").write_bytes((Path(sequences) / "manifest.json").read_bytes())
        (root / "source-split.json").write_bytes((Path(sequences) / "source-split.json").read_bytes())
        train_x, train_y = normal_arrays(dataset, "train")
        prep = ForecastPreprocessor.fit(train_x, train_y)
        validation_x, validation_y = normal_arrays(dataset, "validation")
        started = time.perf_counter()
        model, training = fit_gru(prep, train_x, train_y, validation_x, validation_y, epochs=epochs, seed=seed)
        training["training_seconds_workstation"] = time.perf_counter() - started
        training.update(training_examples=len(train_x), normal_validation_examples=len(validation_x),
                        parameters=sum(p.numel() for p in model.parameters()))
        _save(root / "training.json", training)
        # Freeze all weights and preprocessing before reading test observations.
        save_forecaster(root, model, prep, config)
        restored, restored_prep, _ = load_forecaster(root)
        np.testing.assert_allclose(forecast(model, prep, validation_x),
                                   forecast(restored, restored_prep, validation_x), rtol=0, atol=0, equal_nan=True)
        model, prep = restored, restored_prep
        del train_x, train_y, validation_x, validation_y
        report = {"training": training, "partitions": {}}
        for partition in ("validation", "test"):
            folder = root / "predictions" / partition
            folder.mkdir(parents=True)
            targets, predictions, references, cases = [], [], [], []
            for session, x, y, times in dataset.sessions(partition):
                predicted, reference = forecast(model, prep, x), persistence(x)
                if not np.isfinite(predicted[:, :2]).all() or (prep.current_enabled and not np.isfinite(predicted).all()):
                    raise ValueError("Nonfinite GRU forecast.")
                with (folder / (session["run_id"] + ".jsonl")).open("x", encoding="utf-8") as stream:
                    for t, actual, gru, baseline in zip(times, y, predicted, reference):
                        stream.write(json.dumps({"prediction_ms": t - config["horizon_samples"] * 50,
                                                 "target_ms": t, "actual": _numbers(actual),
                                                 "gru": _numbers(gru), "persistence": _numbers(baseline)},
                                                allow_nan=False) + "\n")
                targets.append(y)
                predictions.append(predicted)
                references.append(reference)
                cases.extend([session["case"]] * len(y))
            y, predicted, reference = map(np.concatenate, (targets, predictions, references))
            cases = np.array(cases)
            def metrics(mask):
                return {"gru": forecast_metrics(y[mask], predicted[mask], reference[mask]),
                        "persistence": forecast_metrics(y[mask], reference[mask], reference[mask])}
            report["partitions"][partition] = {
                "overall": metrics(np.ones(len(y), dtype=bool)),
                "by_case": {case: metrics(cases == case) for case in sorted(set(cases))},
            }
        _save(root / "report.json", report)
        _write_report(root / "report.md", report)
        metadata["report_sha256"] = hashlib.sha256((root / "report.json").read_bytes()).hexdigest()
        metadata["status"] = "completed"
    except BaseException:
        metadata["status"] = "failed"
        raise
    finally:
        _save(root / "manifest.json", metadata)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sequences", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        run_experiment(args.sequences, args.output, epochs=args.epochs, seed=args.seed)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, AssertionError) as error:
        parser.exit(1, f"GRU experiment failed: {error}\n")
    print(f"GRU forecast experiment completed: {args.output}")
    print("Development pilot only; no anomaly alarms, Qt integration or hardware validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
