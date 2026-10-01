"""Compare four frozen alarm methods on the same synthetic gate timeline."""

import argparse
import hashlib
from pathlib import Path
import platform

import joblib
import numpy as np
import sklearn
import torch

from ml.gate_detectors import GateDetectors, calibrate
from ml.gate_evaluation import LABEL_VERSION, EVALUATION_VERSION, counterfactual_labels, evaluate
from ml.gate_feature_export import _decode, _read, _rows
from ml.gate_features import MAX_EVENTS, MAX_SAMPLES, extract_features
from ml.gate_forecast_data import FEATURE_NAMES, SequenceDataset
from ml.gate_forecast_metrics import persistence
from ml.gate_gru import forecast, load_forecaster
from ml.gate_residuals import SCORE_VERSION, ResidualScaler, common_labels, timed_alarms
from ml.gate_sequence_export import _save
from simulator.__main__ import code_version
from simulator.gate_pilot import simulate_session

METHODS = ("gru", "persistence", "isolation_forest", "temporal_rules")
CONFIG = {"history_samples": 20, "horizon_samples": 1, "aggregate_window_ms": 1000}
TIMES = list(range(1000, 8001, 50))


def pilot_data(session, entry, x, y, times, *, with_labels=False):
    """Verify raw provenance and exact sequence alignment before using labels."""
    source = Path(session["path"])
    raw_obs, raw_events = _read(source / "observations.jsonl"), _read(source / "events.jsonl")
    for raw, key in ((raw_obs, "observations_sha256"), (raw_events, "events_sha256")):
        if hashlib.sha256(raw).hexdigest() != entry[key]:
            raise ValueError("Raw pilot hash differs from the sequence export.")
    obs, events = _rows(raw_obs, MAX_SAMPLES), _rows(raw_events, MAX_EVENTS)
    rows = extract_features(obs, events)
    if (times != TIMES or [o["logical_ms"] for o in obs] != list(range(0, 8001, 50))
            or obs[0]["run_id"] != session["run_id"]):
        raise ValueError("This comparison requires complete eight-second pilot sessions.")
    features = [r["x"] for r in rows]
    matrix = np.array([[r[k] for k in FEATURE_NAMES] for r in features], dtype=np.float32)
    expected_x = np.stack([matrix[i - 20:i] for i in range(20, 161)])
    expected_y = np.array([[o[k] for k in ("closed_contact", "open_contact", "current_a")]
                           for o in obs[20:]], dtype=np.float32)
    np.testing.assert_array_equal(x, expected_x)
    np.testing.assert_array_equal(y, expected_y)
    if any(o["current_a"] is None for o in obs):
        raise ValueError("The common three-channel comparison requires current measurements.")
    truth = _decode(_read(source / "ground_truth.json"))
    if any(truth[k] != session[k] for k in ("case", "profile", "paired_group")):
        raise ValueError("Ground truth differs from frozen session metadata.")
    kwargs = dict(seed=truth["seed"], run_id=session["run_id"], profile=session["profile"])
    generated = simulate_session(case=session["case"], **kwargs)
    if (obs, events) != generated[:2]:
        raise ValueError("Raw session no longer matches the supported default-node pilot generator.")
    labels = None
    if with_labels:
        reference = simulate_session(case="normal", **kwargs)
        labels = common_labels(counterfactual_labels(obs, events, *reference[:2]), times)
    return features, labels


def load_inputs(sequences, gru_root):
    dataset = SequenceDataset(sequences)
    gru_root = Path(gru_root)
    raw_manifest = _read(gru_root / "manifest.json")
    source = _decode(raw_manifest)
    if (source["status"] != "completed" or source["experiment_version"] != "gate-gru-forecast-1"
            or source["source_manifest_sha256"] != dataset.manifest_sha256
            or source["sequence_config"] != CONFIG
            or any(dataset.manifest[k] != v for k, v in CONFIG.items())
            or _read(gru_root / "source-split.json") != _read(Path(sequences) / "source-split.json")):
        raise ValueError("GRU and sequence export must share a completed, identical 20/1 pilot split.")
    model, prep, config = load_forecaster(gru_root)
    if config["sequence_config"] != CONFIG or not prep.current_enabled:
        raise ValueError("Expected a three-channel GRU with the common sequence configuration.")
    return dataset, model, prep, source, raw_manifest


def method_scores(baselines, scalers, features, actual, predicted, reference):
    return {"gru": scalers["gru"].scores(actual, predicted),
            "persistence": scalers["persistence"].scores(actual, reference),
            **baselines.scores(features[20:])}


def write_report(path, report):
    lines = ["# Alarmy GRU i metody odniesienia", "",
             "Syntetyczny pilot rozwojowy. Wspólna ocena od 1000 do 8000 ms każdej sesji.",
             "Progi: maksimum wyniku normalnej walidacji, alarm po 3 kolejnych przekroczeniach.", "",
             "| Metoda | Wykryte zdarzenia | Pominięte | Niedopasowane alarmy | Alarmy na normalnych sesjach |",
             "|---|---:|---:|---:|---:|"]
    for name, result in report["partitions"]["test"].items():
        r = result["overall"]
        lines.append(f"| {name} | {r['detected_events']}/{r['events']} | {r['missed_events']} | "
                     f"{r['unmatched_alarms']} | {r['normal_alarms']} |")
    exposure = report["partitions"]["test"]["gru"]["overall"]["normal_duration_ms"] / 1000
    lines.extend(["", f"Oceniany czas normalnej pracy: **{exposure:g} s**, bez rozgrzewki.",
                  "Nie porównuj bezpośrednio z raportami obejmującymi pełne 8 s sesji.",
                  "Niedopasowane alarmy obejmują również dodatkowe początki alarmów podczas usterki.",
                  "report.json zawiera opóźnienia detekcji, wyniki według przypadku i miary zdarzeń.",
                  "To nie nowy test końcowy, benchmark cyberataków ani potwierdzenie działania na sprzęcie.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def run_experiment(sequences, gru_root, output):
    torch.set_num_threads(1)
    dataset, gru, prep, source, raw_manifest = load_inputs(sequences, gru_root)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    metadata = {"status": "running", "experiment_version": "gate-alarms-1",
                "score_version": SCORE_VERSION, "label_version": LABEL_VERSION,
                "evaluation_version": EVALUATION_VERSION, "code_version": code_version(),
                "sequence_manifest_sha256": dataset.manifest_sha256,
                "gru_manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
                "baseline_seed": source["seed"], "evaluation_start_ms": 1000, "evaluation_end_ms": 8000,
                "versions": {"python": platform.python_version(), "numpy": np.__version__,
                             "torch": str(torch.__version__), "sklearn": sklearn.__version__},
                "limitations": ["previously inspected same-family development data",
                                "normal validation reused for GRU selection and alarm calibration",
                                "fixed 20/1 windows, complete sampling and all three channels required",
                                "not a cybersecurity attack benchmark, live Qt detector or hardware validation"]}
    _save(root / "manifest.json", metadata)
    try:
        (root / "source-gru-manifest.json").write_bytes(raw_manifest)
        for name in ("manifest.json", "source-split.json"):
            (root / ("sequences-" + name)).write_bytes(_read(Path(sequences) / name))
        frozen_gru = root / "gru"
        frozen_gru.mkdir()
        for name in ("model.json", "weights.pt"):
            (frozen_gru / name).write_bytes((Path(gru_root) / name).read_bytes())
        metadata["gru_model_sha256"] = hashlib.sha256((frozen_gru / "model.json").read_bytes()).hexdigest()
        train_features, actual, predicted, reference = [], [], [], []
        for session, x, y, times in dataset.sessions("train", normal_only=True):
            features, _ = pilot_data(session, dataset.entries["train", session["run_id"]], x, y, times)
            train_features.extend(features)
            actual.append(y)
            predicted.append(forecast(gru, prep, x))
            reference.append(persistence(x))
        actual, predicted, reference = map(np.concatenate, (actual, predicted, reference))
        scalers = {"gru": ResidualScaler.fit(actual, predicted),
                   "persistence": ResidualScaler.fit(actual, reference)}
        baselines = GateDetectors.fit(train_features, seed=source["seed"])
        calibration = {name: [] for name in METHODS}
        for session, x, y, times in dataset.sessions("validation", normal_only=True):
            features, _ = pilot_data(session, dataset.entries["validation", session["run_id"]], x, y, times)
            scores = method_scores(baselines, scalers, features, y, forecast(gru, prep, x), persistence(x))
            for name, values in scores.items():
                calibration[name].extend(values)
        thresholds = {name: calibrate(values) for name, values in calibration.items()}
        frozen = {"thresholds": thresholds, "scales": {k: list(v.scales) for k, v in scalers.items()},
                  "target_names": ["closed_contact", "open_contact", "current_a"],
                  "scale_policy": "RMS residual on normal training targets; native-unit floor 1e-6",
                  "score_policy": "maximum absolute residual divided by its channel scale",
                  "alarm_policy": "strict > max normal validation score, 3 consecutive 50 ms samples",
                  "training_forecasts": len(actual), "baseline_training_rows": len(train_features),
                  "normal_validation_samples": len(calibration["gru"]),
                  "rule_limits": baselines.rule_limits}
        joblib.dump(baselines, root / "baselines.joblib")
        _save(root / "calibration.json", frozen)
        report = {"calibration": frozen, "partitions": {}}
        # All thresholds and scales are frozen before any fault/test data are read here.
        for partition in ("validation", "test"):
            records = {name: [] for name in METHODS}
            predictions_dir, labels_dir = root / "predictions" / partition, root / "labels" / partition
            predictions_dir.mkdir(parents=True)
            labels_dir.mkdir(parents=True)
            for session, x, y, times in dataset.sessions(partition):
                features, labels = pilot_data(session, dataset.entries[partition, session["run_id"]],
                                              x, y, times, with_labels=True)
                scores = method_scores(baselines, scalers, features, y, forecast(gru, prep, x), persistence(x))
                flags = {name: timed_alarms(times, values, thresholds[name]) for name, values in scores.items()}
                for name in METHODS:
                    records[name].append({"normal": session["case"] == "normal", "case": session["case"],
                                          "labels": labels, "alarms": flags[name]})
                _save(predictions_dir / (session["run_id"] + ".json"),
                      {"logical_ms": times, "scores": scores, "alarms": flags})
                _save(labels_dir / (session["run_id"] + ".json"), {"logical_ms": times, "labels": labels})
            report["partitions"][partition] = {
                name: {"overall": evaluate(rows),
                       "by_case": {case: evaluate([r for r in rows if r["case"] == case])
                                   for case in sorted({r["case"] for r in rows})}}
                for name, rows in records.items()}
        _save(root / "report.json", report)
        write_report(root / "report.md", report)
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
    parser.add_argument("gru", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run_experiment(args.sequences, args.gru, args.output)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, AssertionError) as error:
        parser.exit(1, f"Alarm comparison failed: {error}\n")
    print(f"Completed four-method development comparison: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
