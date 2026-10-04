"""Inspect frozen GRU alarm misses on validation only, with checked provenance."""

import argparse
from collections import Counter
import hashlib
from pathlib import Path

import numpy as np
import torch

from ml.gate_alarm_diagnostics import diagnose_events
from ml.gate_alarm_experiment import load_inputs, pilot_data
from ml.gate_evaluation import alarms, evaluate
from ml.gate_feature_export import _decode, _read, _rows
from ml.gate_features import MAX_EVENTS
from ml.gate_gru import forecast
from ml.gate_residuals import ResidualScaler, residuals, timed_alarms
from ml.gate_sequence_export import _save
from simulator.__main__ import code_version


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def run_diagnostics(sequences, gru_root, alarm_root, output):
    torch.set_num_threads(1)
    dataset, model, prep, _, gru_manifest = load_inputs(sequences, gru_root)
    alarm_root, root = Path(alarm_root), Path(output)
    raw_manifest = _read(alarm_root / "manifest.json")
    manifest = _decode(raw_manifest)
    raw_report = _read(alarm_root / "report.json")
    calibration_raw = _read(alarm_root / "calibration.json")
    calibration = _decode(calibration_raw)
    if (manifest["status"] != "completed" or manifest["experiment_version"] != "gate-alarms-1"
            or manifest["sequence_manifest_sha256"] != dataset.manifest_sha256
            or manifest["gru_manifest_sha256"] != digest(gru_manifest)
            or manifest["gru_model_sha256"] != digest(_read(Path(gru_root) / "model.json"))
            or manifest["report_sha256"] != digest(raw_report)
            or _decode(raw_report)["calibration"] != calibration):
        raise ValueError("Frozen alarm provenance or calibration differs.")
    scaler = ResidualScaler(tuple(calibration["scales"]["gru"]))
    threshold = calibration["thresholds"]["gru"]
    root.mkdir(parents=True, exist_ok=False)
    metadata = {"status": "running", "diagnostic_version": "gate-validation-diagnostics-1",
                "partition": "validation", "code_version": code_version(),
                "alarm_manifest_sha256": digest(raw_manifest),
                "calibration_sha256": digest(calibration_raw),
                "sequence_manifest_sha256": dataset.manifest_sha256,
                "gru_manifest_sha256": digest(gru_manifest),
                "limitations": ["descriptive development validation, not final evaluation",
                                "same frozen threshold; persistence 1/3/5 is sensitivity only",
                                "no fitting and no test partition data read"]}
    _save(root / "manifest.json", metadata)
    try:
        (root / "timelines").mkdir()
        events, sessions, hashes = [], [], {}
        records = {str(p): [] for p in (1, 3, 5)}
        for session, x, actual, times in dataset.sessions("validation"):
            run_id = session["run_id"]
            features, labels = pilot_data(session, dataset.entries["validation", run_id],
                                         x, actual, times, with_labels=True)
            predicted = forecast(model, prep, x)
            scores = scaler.scores(actual, predicted)
            flags = timed_alarms(times, scores, threshold)
            saved_raw = _read(alarm_root / "predictions" / "validation" / (run_id + ".json"))
            saved = _decode(saved_raw)
            label_raw = _read(alarm_root / "labels" / "validation" / (run_id + ".json"))
            if (saved["logical_ms"] != times or saved["alarms"]["gru"] != flags
                    or _decode(label_raw) != {"logical_ms": times, "labels": labels}):
                raise ValueError("Saved validation timeline differs from recomputed evidence.")
            np.testing.assert_allclose(saved["scores"]["gru"], scores, rtol=1e-6, atol=1e-8)
            hashes[run_id] = {"prediction_sha256": digest(saved_raw), "labels_sha256": digest(label_raw)}
            rows = diagnose_events(times, scores, labels, threshold)
            events.extend({"run_id": run_id, "case": session["case"], "profile": session["profile"], **r}
                          for r in rows)
            for p in records:
                records[p].append({"normal": session["case"] == "normal", "case": session["case"],
                                   "labels": labels, "alarms": alarms(scores, threshold, persistence=int(p))})
            timeline = {"run_id": run_id, "case": session["case"], "profile": session["profile"],
                        "logical_ms": times, "actual": actual.tolist(), "predicted": predicted.tolist(),
                        "scaled_residuals": (residuals(actual, predicted) / scaler.scales).tolist(),
                        "scores": scores, "threshold": threshold, "alarms": flags, "labels": labels,
                        "pending_commands": [r["pending_commands"] for r in features[20:]],
                        "commands": _rows(_read(Path(session["path"]) / "events.jsonl"), MAX_EVENTS)}
            _save(root / "timelines" / (run_id + ".json"), timeline)
            sessions.append({"run_id": run_id, "case": session["case"], "profile": session["profile"],
                             "peak_score": max(scores), "events": len(rows)})
        cases = sorted({s["case"] for s in sessions})
        report = {"partition": "validation", "threshold": threshold, "sessions": sessions,
                  "events": events, "by_case": {
                      case: dict(Counter(r["reason"] for r in events if r["case"] == case)) for case in cases},
                  "persistence_sensitivity": {p: {
                      "overall": evaluate(rows),
                      "by_case": {c: evaluate([r for r in rows if r["case"] == c]) for c in cases}}
                      for p, rows in records.items()}}
        expected = _decode(raw_report)["partitions"]["validation"]["gru"]
        if report["persistence_sensitivity"]["3"] != expected:
            raise ValueError("Diagnostic evaluation differs from frozen validation report.")
        _save(root / "report.json", report)
        metadata.update(status="completed", report_sha256=digest(_read(root / "report.json")),
                        validation_sources=hashes)
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
    parser.add_argument("alarms", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run_diagnostics(args.sequences, args.gru, args.alarms, args.output)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, AssertionError) as error:
        parser.exit(1, f"Validation diagnostics failed: {error}\n")
    print(report["by_case"])
    print(f"Validation diagnostics saved: {args.output}")


if __name__ == "__main__":
    main()
