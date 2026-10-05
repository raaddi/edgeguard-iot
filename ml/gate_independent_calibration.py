"""Independent normal calibration of frozen models; a development experiment."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform

import joblib
import numpy as np
import sklearn
import torch

from ml.gate_alarm_experiment import CONFIG, METHODS, method_scores
from ml.gate_calibration import calibrate_sessions
from ml.gate_detectors import GateDetectors
from ml.gate_evaluation import LABEL_VERSION, EVALUATION_VERSION, counterfactual_labels, evaluate
from ml.gate_features import FEATURE_VERSION, extract_features
from ml.gate_forecast_data import FEATURE_NAMES
from ml.gate_forecast_metrics import persistence
from ml.gate_gru import forecast, load_forecaster
from ml.gate_residuals import SCORE_VERSION, ResidualScaler, common_labels, residuals, timed_alarms
from ml.gate_sequence_export import _save
from ml.gate_sequences import TARGET_NAMES
from simulator.__main__ import code_version
from simulator.gate_pilot import CASES, simulate_session
from simulator.gate_research_suite import CYCLES, CONDITIONS, CALIBRATION_CONDITIONS

CALIBRATION_SEEDS = tuple(range(1000, 1016))
EVALUATION_SEEDS = tuple(range(2000, 2016))
POLICIES = ("sample_max", "sustained_max")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_frozen(root):
    """Only load baselines.joblib from a trusted, locally produced alarm artifact."""
    root = Path(root)
    def read(name):
        return json.loads((root / name).read_text(encoding="utf-8"))
    manifest, frozen = read("manifest.json"), read("calibration.json")
    if (manifest["status"] != "completed" or manifest["experiment_version"] != "gate-alarms-1"
            or digest(root / "report.json") != manifest["report_sha256"]
            or digest(root / "gru/model.json") != manifest["gru_model_sha256"]
            or digest(root / "source-gru-manifest.json") != manifest["gru_manifest_sha256"]
            or digest(root / "sequences-manifest.json") != manifest["sequence_manifest_sha256"]
            or read("report.json")["calibration"] != frozen):
        raise ValueError("Frozen alarm artifact provenance does not match.")
    model, prep, config = load_forecaster(root / "gru")
    if config["sequence_config"] != CONFIG or not prep.current_enabled:
        raise ValueError("Expected the frozen 20/1 three-channel model.")
    groups = read("sequences-source-split.json")["group_assignments"]
    used = {int(group.removeprefix("gate-v1-seed-")) for group in groups}
    if used & set(CALIBRATION_SEEDS + EVALUATION_SEEDS):
        raise ValueError("Independent seeds overlap the original model split.")
    baselines = joblib.load(root / "baselines.joblib")
    if (not isinstance(baselines, GateDetectors) or baselines.feature_names != FEATURE_NAMES
            or baselines.rule_limits != frozen["rule_limits"]):
        raise ValueError("Frozen baseline features or rule limits differ.")
    scalers = {k: ResidualScaler(tuple(v)) for k, v in frozen["scales"].items()}
    hashes = {name: digest(root / name) for name in ("manifest.json", "calibration.json",
        "baselines.joblib", "gru/model.json", "gru/weights.pt", "sequences-source-split.json")}
    return model, prep, baselines, scalers, hashes


def score_session(frozen, obs, events):
    model, prep, baselines, scalers, _ = frozen
    features = [row["x"] for row in extract_features(obs, events)]
    matrix = np.asarray([[row[k] for k in FEATURE_NAMES] for row in features], dtype=np.float32)
    x = np.stack([matrix[i - 20:i] for i in range(20, len(matrix))])
    actual = np.asarray([[row[k] for k in TARGET_NAMES] for row in obs[20:]], dtype=np.float32)
    predicted = forecast(model, prep, x)
    scores = method_scores(baselines, scalers, features, actual, predicted, persistence(x))
    return {"logical_ms": [row["logical_ms"] for row in obs[20:]],
            "actual": actual.tolist(), "predicted": predicted.tolist(), "scores": scores,
            "scaled_residuals": (residuals(actual, predicted) / scalers["gru"].scales).tolist(),
            "pending_commands": [row["pending_commands"] for row in features[20:]]}


def generate(root, partition, seed, condition, case):
    run_id = f"calibration-v1-{partition}-{condition}-{seed}-{case}"
    obs, events, truth = simulate_session(seed=seed, case=case, run_id=run_id,
                                         settings=CONDITIONS[condition])
    folder = root / "raw" / partition / run_id
    folder.mkdir(parents=True)
    for name, rows in (("observations", obs), ("events", events)):
        (folder / (name + ".jsonl")).write_text(
            "".join(json.dumps(row, allow_nan=False) + "\n" for row in rows), encoding="utf-8")
    _save(folder / "ground_truth.json", truth)
    return obs, events


def aggregate(records):
    return {"overall": evaluate(records),
            "by_case": {k: evaluate([r for r in records if r["case"] == k]) for k in CASES},
            "by_condition": {k: evaluate([r for r in records if r["condition"] == k])
                             for k in CONDITIONS},
            "by_seed": {str(k): evaluate([r for r in records if r["seed"] == k])
                        for k in EVALUATION_SEEDS},
            "sessions": [{"run_id": r["run_id"], "condition": r["condition"],
                          "case": r["case"], "seed": r["seed"], **evaluate([r])} for r in records]}


def run_experiment(alarm_root, output):
    torch.set_num_threads(1)
    frozen = load_frozen(alarm_root)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    manifest = {"experiment_version": "gate-independent-calibration-1", "status": "running",
        "code_version": code_version(), "source_hashes": frozen[-1],
        "calibration_seeds": CALIBRATION_SEEDS, "evaluation_seeds": EVALUATION_SEEDS,
        "conditions": {k: asdict(v) for k, v in CONDITIONS.items()},
        "calibration_conditions": CALIBRATION_CONDITIONS, "sequence_config": CONFIG,
        "feature_version": FEATURE_VERSION, "score_version": SCORE_VERSION,
        "label_version": LABEL_VERSION, "evaluation_version": EVALUATION_VERSION,
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "torch": str(torch.__version__), "sklearn": sklearn.__version__},
        "limitations": ["synthetic development evaluation, not a final thesis test",
                        "independent normal thresholds; existing frozen model and training scales",
                        "short sessions reset from closed; no evidence of continuous long-term operation",
                        "no live GUI inference, physical validation or Raspberry Pi benchmark"]}
    _save(root / "manifest.json", manifest)
    try:
        calibration_rows = []
        for seed in CALIBRATION_SEEDS:
            for condition in CALIBRATION_CONDITIONS:
                obs, events = generate(root, "calibration", seed, condition, "normal")
                values = score_session(frozen, obs, events)
                calibration_rows.append({"run_id": obs[0]["run_id"], "seed": seed,
                                         "condition": condition, **values})
        thresholds = {policy: {} for policy in POLICIES}
        for method in METHODS:
            chosen = calibrate_sessions([r["scores"][method] for r in calibration_rows])
            for policy in POLICIES:
                thresholds[policy][method] = chosen[policy]
                if any(any(timed_alarms(r["logical_ms"], r["scores"][method], chosen[policy]))
                       for r in calibration_rows):
                    raise ValueError("Calibration unexpectedly creates normal alarms.")
        _save(root / "calibration-scores.json", calibration_rows)
        # Persist all thresholds before creating or scoring any evaluation session.
        _save(root / "calibration.json", {"thresholds": thresholds,
            "normal_sessions": len(calibration_rows), "policies": POLICIES,
            "normal_duration_ms": sum(r["logical_ms"][-1] - r["logical_ms"][0] for r in calibration_rows),
            "alarm_policy": "three consecutive strict exceedances on the 50 ms grid"})
        manifest["calibration_sha256"] = digest(root / "calibration.json")
        _save(root / "manifest.json", manifest)
        records = {policy: {method: [] for method in METHODS} for policy in POLICIES}
        for seed in EVALUATION_SEEDS:
            for condition in CONDITIONS:
                reference = generate(root, "evaluation", seed, condition, "normal")
                for case in CASES:
                    obs, events = reference if case == "normal" else generate(root, "evaluation", seed, condition, case)
                    values = score_session(frozen, obs, events)
                    times = values["logical_ms"]
                    labels = common_labels(counterfactual_labels(obs, events, *reference), times)
                    for policy in POLICIES:
                        flags = {m: timed_alarms(times, values["scores"][m], thresholds[policy][m]) for m in METHODS}
                        for method in METHODS:
                            records[policy][method].append({"normal": case == "normal", "case": case,
                                "condition": condition, "seed": seed, "run_id": obs[0]["run_id"],
                                "labels": labels, "alarms": flags[method]})
                        folder = root / "timelines" / policy
                        folder.mkdir(parents=True, exist_ok=True)
                        _save(folder / (obs[0]["run_id"] + ".json"), {
                            **values, "timeline_version": "gate-ml-view-1", "run_id": obs[0]["run_id"],
                            "source": "synthetic", "model_version": "gate-gru-1", "feature_version": FEATURE_VERSION,
                            "case": case, "condition": condition, "seed": seed, "policy": policy,
                            "threshold": thresholds[policy]["gru"], "thresholds": thresholds[policy],
                            "gru_scores": values["scores"]["gru"], "alarms": flags["gru"],
                            "method_alarms": flags, "labels": labels,
                            "commands": [{"logical_ms": e["logical_ms"], "value": e["message"]["value"]}
                                         for e in events if e["kind"] == "command_sent"]})
        report = {"thresholds": thresholds,
                  "policies": {p: {m: aggregate(records[p][m]) for m in METHODS} for p in POLICIES}}
        _save(root / "report.json", report)
        manifest.update(status="completed", report_sha256=digest(root / "report.json"))
    except BaseException:
        manifest["status"] = "failed"
        raise
    finally:
        _save(root / "manifest.json", manifest)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alarm_root", type=Path, help="Trusted local step-16 artifact (includes joblib).")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run_experiment(args.alarm_root, args.output)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, AssertionError) as error:
        parser.exit(1, f"Independent calibration failed: {error}\n")
    print(f"Completed independent development evaluation: {args.output}")


if __name__ == "__main__":
    main()
