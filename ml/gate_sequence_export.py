"""Export grouped forecast examples and evaluate a fixed persistence reference."""

import argparse
import hashlib
import json
from pathlib import Path

from ml.gate_feature_export import _decode, _read, _rows, validate_plan
from ml.gate_features import FEATURE_VERSION, MAX_EVENTS, MAX_SAMPLES, SAMPLE_MS
from ml.gate_persistence import PersistenceMetrics, predict
from ml.gate_sequences import SEQUENCE_VERSION, TARGET_NAMES, iter_sequences, validate_config
from simulator.__main__ import code_version

EXPORT_VERSION = "gate-sequence-export-1"
MAX_EXAMPLES = 100_000


def _save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def export_sequences(split_path, output, *, history_samples=20, horizon_samples=1):
    validate_config(history_samples, horizon_samples)
    split_bytes = _read(split_path)
    plan = _decode(split_bytes)
    validate_plan(plan)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    manifest = {
        "status": "running", "export_version": EXPORT_VERSION,
        "sequence_version": SEQUENCE_VERSION, "feature_version": FEATURE_VERSION,
        "sample_ms": SAMPLE_MS, "history_samples": history_samples,
        "horizon_samples": horizon_samples, "aggregate_window_ms": 1000,
        "target_names": list(TARGET_NAMES), "code_version": code_version(),
        "split_sha256": hashlib.sha256(split_bytes).hexdigest(),
        "excluded_sessions": len(plan["partitions"]["excluded_train_faults"]),
        "sessions": [], "examples": 0,
        "limitations": ["synthetic pilot, not physical validation",
                        "no fitted model, anomaly score or alarm threshold",
                        "overlapping examples are not independent observations",
                        "previously inspected pilot test is development data"],
    }
    _save(root / "manifest.json", manifest)
    report = {"reference": "last observed value, no fitting or imputation",
              "partitions": {}}
    try:
        (root / "source-split.json").write_bytes(split_bytes)
        for partition in ("train", "validation", "test"):
            folder = root / partition
            folder.mkdir()
            overall, by_case = PersistenceMetrics(), {}
            for session in plan["partitions"][partition]:
                source = Path(session["path"])
                obs_bytes = _read(source / "observations.jsonl")
                event_bytes = _read(source / "events.jsonl")
                observations = _rows(obs_bytes, MAX_SAMPLES)
                events = _rows(event_bytes, MAX_EVENTS)
                if not observations or observations[0]["run_id"] != session["run_id"]:
                    raise ValueError("Observation session does not match split plan.")
                rows = iter_sequences(observations, events, history_samples=history_samples,
                                      horizon_samples=horizon_samples)
                metrics = by_case.setdefault(session["case"], PersistenceMetrics())
                target = folder / (session["run_id"] + ".jsonl")
                digest, count = hashlib.sha256(), 0
                with target.open("xb") as stream:
                    for row in rows:
                        if manifest["examples"] >= MAX_EXAMPLES:
                            raise ValueError("Export exceeds 100000 forecast examples.")
                        prediction = predict(row["x"])
                        overall.add(prediction, row["y"])
                        metrics.add(prediction, row["y"])
                        # The reference output stays outside model inputs and targets.
                        payload = (json.dumps(dict(row, persistence=prediction), allow_nan=False)
                                   + "\n").encode("utf-8")
                        stream.write(payload)
                        digest.update(payload)
                        count += 1
                        manifest["examples"] += 1
                manifest["sessions"].append({
                    "run_id": session["run_id"], "partition": partition, "examples": count,
                    "observations_sha256": hashlib.sha256(obs_bytes).hexdigest(),
                    "events_sha256": hashlib.sha256(event_bytes).hexdigest(),
                    "sequences_sha256": digest.hexdigest(),
                })
            report["partitions"][partition] = {
                "overall": overall.report(),
                "by_case": {case: metrics.report() for case, metrics in by_case.items()},
            }
        _save(root / "persistence-report.json", report)
        manifest["status"] = "completed"
    except BaseException:
        manifest["status"] = "failed"
        raise
    finally:
        _save(root / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--history-samples", type=int, default=20)
    parser.add_argument("--horizon-samples", type=int, default=1)
    args = parser.parse_args()
    try:
        result = export_sequences(args.split, args.output, history_samples=args.history_samples,
                                  horizon_samples=args.horizon_samples)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"Sequence export failed: {error}\n")
    print(f"Exported {result['examples']} forecast examples from {len(result['sessions'])} sessions.")
    print(f"Output: {args.output}; fixed persistence reference only, no trained GRU.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
