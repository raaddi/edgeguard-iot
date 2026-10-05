"""Export causal command-response examples; no training or anomaly detection."""

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform

from ml.gate_features import FEATURE_VERSION, SAMPLE_MS
from ml.gate_response_targets import RESPONSE_VERSION, extract_response_examples
from simulator.__main__ import code_version
from simulator.gate import MODEL_VERSION
from simulator.gate_pilot import CASES, DATASET_VERSION, simulate_session
from simulator.gate_research_suite import CONDITIONS, CALIBRATION_CONDITIONS

EXPORT_VERSION = "gate-response-export-1"
HISTORY_SAMPLES = 20
ROLE_SEEDS = {
    "train": tuple(range(3000, 3016)),
    "selection": tuple(range(4000, 4008)),
    "calibration": tuple(range(5000, 5016)),
    "evaluation": tuple(range(6000, 6016)),
}
HISTORICAL_SEEDS = frozenset((*range(42, 62), *range(1000, 1016), *range(2000, 2016)))
PROTOCOL_PATH = Path(__file__).resolve().parents[1] / "docs/step-19-command-response-targets.md"
MAX_SESSIONS = 440


def _save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _jsonl(path, rows):
    path.write_text("".join(json.dumps(row, allow_nan=False) + "\n" for row in rows),
                    encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _validate_roles():
    if set(ROLE_SEEDS) != {"train", "selection", "calibration", "evaluation"}:
        raise ValueError("Expected the four predefined seed roles.")
    seen, count = set(), 0
    for role, seeds in ROLE_SEEDS.items():
        maximum = 8 if role == "selection" else 16
        if (not isinstance(seeds, tuple) or not 1 <= len(seeds) <= maximum
                or any(type(seed) is not int or not 0 <= seed < 2**32 for seed in seeds)
                or len(set(seeds)) != len(seeds)):
            raise ValueError("Expected bounded unique integer seeds for each role.")
        if set(seeds) & (seen | HISTORICAL_SEEDS):
            raise ValueError("Seed roles overlap each other or historical development groups.")
        seen.update(seeds)
        count += len(seeds) * (len(CONDITIONS) * len(CASES) if role == "evaluation"
                               else len(CALIBRATION_CONDITIONS))
    if count > MAX_SESSIONS:
        raise ValueError("Response export exceeds its session budget.")
    return count


def _counts(rows):
    result = {"sessions": len(rows), "commands": sum(row["commands"] for row in rows),
              "examples": sum(len(row["data"]["examples"]) for row in rows),
              "excluded": sum(len(row["data"]["excluded"]) for row in rows)}
    excluded = Counter(item["reason"] for row in rows for item in row["data"]["excluded"])
    result["excluded_reasons"] = dict(sorted(excluded.items()))
    for name in ("ack", "contact"):
        targets = [example["y"][name] for row in rows for example in row["data"]["examples"]]
        reasons = Counter(target["censor_reason"] for target in targets if not target["observed"])
        stats = {"observed": sum(target["observed"] for target in targets),
                 "censored": sum(not target["observed"] for target in targets),
                 "censor_reasons": dict(sorted(reasons.items()))}
        if name == "ack":
            stats.update(accepted=sum(target["accepted"] is True for target in targets),
                         rejected=sum(target["accepted"] is False for target in targets))
        result[name] = stats
    return result


def _grouped_counts(rows, key):
    return {value: _counts([row for row in rows if row[key] == value])
            for value in sorted({row[key] for row in rows})}


def export_responses(output):
    """Generate the frozen development roles into a new local artifact folder."""
    session_count = _validate_roles()
    protocol = PROTOCOL_PATH.read_bytes()
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    role_conditions = {role: tuple(CONDITIONS) if role == "evaluation" else CALIBRATION_CONDITIONS
                       for role in ROLE_SEEDS}
    manifest = {
        "status": "running", "export_version": EXPORT_VERSION,
        "response_version": RESPONSE_VERSION, "feature_version": FEATURE_VERSION,
        "dataset_version": DATASET_VERSION, "simulator_model_version": MODEL_VERSION,
        "session_settings_version": "gate-session-settings-1",
        "source": "synthetic", "code_version": code_version(),
        "python_version": platform.python_version(), "history_samples": HISTORY_SAMPLES,
        "sample_ms": SAMPLE_MS, "aggregate_window_ms": 1000,
        "seed_roles": ROLE_SEEDS, "historical_seeds_excluded": sorted(HISTORICAL_SEEDS),
        "group_assignments": {str(seed): role for role, seeds in ROLE_SEEDS.items() for seed in seeds},
        "role_conditions": role_conditions,
        "role_cases": {role: CASES if role == "evaluation" else ("normal",) for role in ROLE_SEEDS},
        "conditions": {name: asdict(settings) for name, settings in CONDITIONS.items()},
        "protocol_source": "docs/step-19-command-response-targets.md",
        "protocol_file": "protocol.md", "protocol_sha256": hashlib.sha256(protocol).hexdigest(),
        "expected_sessions": session_count, "sessions": [],
        "limitations": ["synthetic development export, not a final thesis test",
                        "causal inputs and future supervised targets kept separate",
                        "paired seeds and repeated commands are not independent observations",
                        "no fitted preprocessing, model, threshold or alarm evaluation",
                        "no physical validation, live inference or Raspberry Pi measurements"],
    }
    _save(root / "manifest.json", manifest)
    rows = []
    try:
        (root / "protocol.md").write_bytes(protocol)
        for role, seeds in ROLE_SEEDS.items():
            for seed in seeds:
                for condition in role_conditions[role]:
                    cases = CASES if role == "evaluation" else ("normal",)
                    for case in cases:
                        run_id = f"response-v1-{role}-{condition}-{seed}-{case}"
                        observations, events, truth = simulate_session(
                            seed=seed, case=case, run_id=run_id, settings=CONDITIONS[condition])
                        data = extract_response_examples(observations, events,
                                                         history_samples=HISTORY_SAMPLES)
                        commands = sum(event["kind"] == "command_sent" for event in events)
                        if (data["response_version"] != RESPONSE_VERSION
                                or len(data["examples"]) + len(data["excluded"]) != commands):
                            raise ValueError("Response examples do not account for the session commands.")
                        raw = root / "raw" / role / run_id
                        raw.mkdir(parents=True)
                        _jsonl(raw / "observations.jsonl", observations)
                        _jsonl(raw / "events.jsonl", events)
                        _save(raw / "ground_truth.json", truth)
                        target = root / "examples" / role / (run_id + ".json")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        _save(target, data)
                        entry = {"run_id": run_id, "role": role, "seed": seed,
                                 "paired_group": truth["paired_group"], "condition": condition,
                                 "case": case, "commands": commands, "examples": len(data["examples"]),
                                 "excluded": len(data["excluded"]),
                                 "observations_file": (raw / "observations.jsonl").relative_to(root).as_posix(),
                                 "events_file": (raw / "events.jsonl").relative_to(root).as_posix(),
                                 "ground_truth_file": (raw / "ground_truth.json").relative_to(root).as_posix(),
                                 "examples_file": target.relative_to(root).as_posix(),
                                 "observations_sha256": digest(raw / "observations.jsonl"),
                                 "events_sha256": digest(raw / "events.jsonl"),
                                 "ground_truth_sha256": digest(raw / "ground_truth.json"),
                                 "examples_sha256": digest(target)}
                        manifest["sessions"].append(entry)
                        rows.append({**entry, "data": data})
        report = {"overall": _counts(rows),
                  "by_role": {role: {"overall": _counts([row for row in rows if row["role"] == role]),
                                      "by_case": _grouped_counts([row for row in rows if row["role"] == role], "case"),
                                      "by_condition": _grouped_counts([row for row in rows if row["role"] == role], "condition")}
                              for role in ROLE_SEEDS},
                  "by_case": _grouped_counts(rows, "case"),
                  "by_condition": _grouped_counts(rows, "condition"),
                  "sessions": [{"run_id": row["run_id"], "role": row["role"], "seed": row["seed"],
                                "condition": row["condition"], "case": row["case"], **_counts([row])}
                               for row in rows]}
        _save(root / "report.json", report)
        manifest.update(status="completed", report_sha256=digest(root / "report.json"),
                        commands=report["overall"]["commands"], examples=report["overall"]["examples"],
                        excluded=report["overall"]["excluded"])
    except BaseException:
        manifest["status"] = "failed"
        raise
    finally:
        _save(root / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = export_responses(args.output)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"Response export failed: {error}\n")
    print(f"Exported {result['examples']} response examples from {len(result['sessions'])} sessions.")
    print(f"Output: {args.output}; supervised data only, no trained model or alarm evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
