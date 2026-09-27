"""One-command synthetic gate pilot: generate, split, fit, calibrate, evaluate."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import time
from uuid import uuid4

import joblib
import numpy as np
import scipy
import sklearn

from ml.gate_detectors import GateDetectors, calibrate
from ml.gate_evaluation import LABEL_VERSION, EVALUATION_VERSION, alarms, counterfactual_labels, evaluate
from ml.gate_feature_export import export_features
from ml.gate_features import FEATURE_VERSION
from ml.gate_split import load_sessions, split_sessions
from simulator.__main__ import code_version
from simulator.gate_pilot import CASES, PROFILES, run_suite, simulate_session


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_report(path, report):
    lines = ["# Pierwszy pilot ML bramy", "",
             "Dane syntetyczne. Wynik nie potwierdza działania na sprzęcie.", "",
             "| Metoda | Wykryte zdarzenia | Pominięte | Niedopasowane alarmy | Alarmy / h normalnej pracy |",
             "|---|---:|---:|---:|---:|"]
    for name, result in report["partitions"]["test"].items():
        r = result["overall"]
        lines.append(f"| {name} | {r['detected_events']}/{r['events']} | {r['missed_events']} | "
                     f"{r['unmatched_alarms']} | {r['false_alarms_per_normal_hour']} |")
    exposure = report["partitions"]["test"]["isolation_forest"]["overall"]["normal_duration_ms"] / 1000
    lines.extend(["", f"Normalna ekspozycja testowa: **{exposure:g} s**. Zero alarmów w tym",
                  "krótkim czasie nie gwarantuje braku fałszywych alarmów w przyszłości.", "",
                  "Reguły i ML mają próg ustalony na normalnej walidacji przed odczytem testu.",
                  "Przedziały etykiet oznaczają rozbieżność od sparowanej symulacji bez usterki.",
                  "Nie są to chwile uszkodzenia prawdziwego mechanizmu.", "",
                  "Pełne liczniki, wyniki według rodzaju usterki i opóźnienia są w report.json.",
                  "Predykcje i etykiety są zapisane osobno. Nie poprawiamy modelu pod ten test.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def load_session(session, feature_root, partition):
    """Internal runner inputs only: verify recorded raw hashes before labeling."""
    manifest = json.loads((feature_root / "manifest.json").read_text(encoding="utf-8"))
    entry = next(s for s in manifest["sessions"] if s["run_id"] == session["run_id"])
    if manifest["status"] != "completed" or entry["partition"] != partition:
        raise ValueError("Feature export is incomplete or partition differs.")
    source = Path(session["path"])
    for name, key in (("observations.jsonl", "observations_sha256"), ("events.jsonl", "events_sha256")):
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != entry[key]:
            raise ValueError("Raw data changed after feature export.")
    rows = read_rows(feature_root / partition / (session["run_id"] + ".jsonl"))
    observations, events = read_rows(source / "observations.jsonl"), read_rows(source / "events.jsonl")
    truth = json.loads((source / "ground_truth.json").read_text(encoding="utf-8"))
    if (truth["case"] != session["case"] or truth["profile"] != session["profile"]
            or truth["paired_group"] != session["paired_group"]):
        raise ValueError("Ground truth differs from the frozen split.")
    kwargs = dict(seed=truth["seed"], run_id=session["run_id"], profile=truth["profile"])
    regenerated = simulate_session(case=truth["case"], **kwargs)
    if (observations, events) != regenerated[:2]:
        raise ValueError("Runner data no longer matches its generator; refusing counterfactual labels.")
    reference = simulate_session(case="normal", **kwargs)
    labels = counterfactual_labels(observations, events, *reference[:2])
    if [r["logical_ms"] for r in rows] != [o["logical_ms"] for o in observations]:
        raise ValueError("Features and labels are misaligned.")
    return rows, labels


def run_experiment(output, *, groups=20, seed=42):
    if type(groups) is not int or not 5 <= groups <= 25:
        raise ValueError("Use 5..25 paired groups per profile.")
    if type(seed) is not int or not 0 <= seed <= 2**32 - groups:
        raise ValueError("Invalid seed range.")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    metadata = {"status": "running", "experiment_version": "gate-baseline-1",
                "feature_version": FEATURE_VERSION, "label_version": LABEL_VERSION,
                "evaluation_version": EVALUATION_VERSION, "code_version": code_version(),
                "groups": groups, "seed": seed, "profiles": list(PROFILES), "cases": list(CASES),
                "training_order": "paired_group, profile; independent of file paths and UUIDs",
                "versions": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                             "numpy": np.__version__, "scipy": scipy.__version__, "joblib": joblib.__version__},
                "calibration_policy": "max normal validation score, strict >, three consecutive samples",
                "limitations": ["illustrative synthetic physics", "four fixed usage profiles",
                                "seed-group split, not unseen-profile test", "short normal exposure",
                                "not a cybersecurity attack benchmark or physical validation"]}
    write_json(root / "manifest.json", metadata)
    try:
        suites = [run_suite(output=root / "raw", suite_id=f"{p}-seed-{seed}", profile=p, seed=seed,
                            sessions_per_case=groups) for p in PROFILES]
        split = split_sessions(load_sessions(suites), seed=seed)
        write_json(root / "split.json", split)
        feature_root = root / "features"
        export_features(root / "split.json", feature_root)
        train = []
        for session in sorted(split["partitions"]["train"], key=lambda s: (s["paired_group"], s["profile"])):
            rows, labels = load_session(session, feature_root, "train")
            if session["case"] != "normal" or any(labels):
                raise ValueError("Only normal sessions may enter training.")
            train.extend(r["x"] for r in rows)
        started = time.perf_counter()
        model = GateDetectors.fit(train, seed=seed)
        training_seconds = time.perf_counter() - started
        normal_scores = {name: [] for name in ("isolation_forest", "temporal_rules")}
        for session in split["partitions"]["validation"]:
            if session["case"] != "normal":
                continue
            rows, labels = load_session(session, feature_root, "validation")
            if any(labels):
                raise ValueError("Normal calibration session has positive labels.")
            for name, values in model.scores([r["x"] for r in rows]).items():
                normal_scores[name].extend(values)
        thresholds = {name: calibrate(values) for name, values in normal_scores.items()}
        # Freeze and save both methods before reading any test session.
        joblib.dump(model, root / "detectors.joblib")
        frozen = {"thresholds": thresholds, "feature_names": model.feature_names,
                  "rule_limits": model.rule_limits, "training_rows": len(train),
                  "training_sessions": len(split["partitions"]["train"]),
                  "normal_validation_rows": len(normal_scores["isolation_forest"]),
                  "training_seconds_workstation": training_seconds,
                  "iforest_parameters": model.forest.get_params()}
        write_json(root / "calibration.json", frozen)
        report = {"calibration": frozen, "partitions": {}}
        prediction_root = root / "predictions"
        prediction_root.mkdir()
        for partition in ("validation", "test"):
            records = {name: [] for name in thresholds}
            for session in split["partitions"][partition]:
                rows, labels = load_session(session, feature_root, partition)
                scores = model.scores([r["x"] for r in rows])
                flags = {name: alarms(values, thresholds[name]) for name, values in scores.items()}
                for name in thresholds:
                    records[name].append({"normal": session["case"] == "normal", "case": session["case"],
                                          "labels": labels, "alarms": flags[name]})
                write_json(prediction_root / (session["run_id"] + ".json"), {
                    "partition": partition, "logical_ms": [r["logical_ms"] for r in rows],
                    "scores": scores, "alarms": flags,
                })
                # Labels are separate, never stored in the model's feature input.
                label_dir = root / "labels"
                label_dir.mkdir(exist_ok=True)
                write_json(label_dir / (session["run_id"] + ".json"), {"labels": labels, "case": session["case"]})
            report["partitions"][partition] = {
                name: {"overall": evaluate(rows),
                       "by_case": {case: evaluate([r for r in rows if r["case"] == case]) for case in CASES}}
                for name, rows in records.items()
            }
        write_json(root / "report.json", report)
        write_report(root / "report.md", report)
        metadata["status"] = "completed"
    except BaseException:
        metadata["status"] = "failed"
        raise
    finally:
        write_json(root / "manifest.json", metadata)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--groups", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    root = args.output or Path(__file__).resolve().parents[1] / "experiments" / "runs" / ("ml-" + str(uuid4()))
    try:
        report = run_experiment(root, groups=args.groups, seed=args.seed)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Experiment failed: {error}\n")
    print(f"Synthetic ML pilot completed: {root}")
    for name, result in report["partitions"]["test"].items():
        r = result["overall"]
        print(f"{name}: events={r['detected_events']}/{r['events']}, "
              f"unmatched alarms={r['unmatched_alarms']}, normal false alarms/h={r['false_alarms_per_normal_hour']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
