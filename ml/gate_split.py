"""Plan a grouped pilot split before feature/window creation; no training."""

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from simulator.__main__ import code_version
from simulator.gate_pilot import CASES, PROFILES


def load_sessions(roots):
    sessions, seen = [], set()
    for root in roots:
        root = Path(root).resolve()
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if (manifest.get("status") != "completed"
                or manifest.get("dataset_version") not in {"gate-pilot-0.1", "gate-pilot-0.2"}
                or manifest.get("model_version") != "illustrative-gate-v1"):
            raise ValueError("Expected a completed, supported gate pilot.")
        if not manifest.get("sessions"):
            raise ValueError("Empty pilot.")
        for entry in manifest["sessions"]:
            run_id = entry["run_id"]
            if str(UUID(run_id)) != run_id or run_id in seen:
                raise ValueError("Invalid or duplicate session ID.")
            folder = (root / run_id).resolve()
            if folder.parent != root:
                raise ValueError("Session directory escapes its pilot.")
            truth = json.loads((folder / "ground_truth.json").read_text(encoding="utf-8"))
            seed = truth["seed"]
            if (type(seed) is not int or not 0 <= seed < 2**32
                    or truth["paired_group"] != f"gate-v1-seed-{seed}"
                    or truth["case"] not in CASES
                    or truth.get("profile", "standard") not in PROFILES):
                raise ValueError("Invalid grouping metadata.")
            if not all((folder / name).is_file() for name in ("observations.jsonl", "events.jsonl")):
                raise ValueError("Missing session observations or events.")
            seen.add(run_id)
            sessions.append({"run_id": run_id, "path": str(folder),
                             "paired_group": truth["paired_group"], "case": truth["case"],
                             "profile": truth.get("profile", "standard")})
    return sessions


def split_sessions(sessions, *, seed=42):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("Split seed must be in 0..2**32-1.")
    if len({s["run_id"] for s in sessions}) != len(sessions):
        raise ValueError("Duplicate session ID.")
    groups = sorted({s["paired_group"] for s in sessions},
                    key=lambda g: (hashlib.sha256(f"{seed}/{g}".encode()).hexdigest(), g))
    if len(groups) < 3:
        raise ValueError("At least three paired groups are required; generate more sessions.")
    evaluation_count = max(1, len(groups) // 5)
    train_end = len(groups) - 2 * evaluation_count
    assignments = {g: "train" if i < train_end else
                   "validation" if i < train_end + evaluation_count else "test"
                   for i, g in enumerate(groups)}
    partitions = {name: [] for name in ("train", "validation", "test", "excluded_train_faults")}
    for session in sorted(sessions, key=lambda s: s["run_id"]):
        partition = assignments[session["paired_group"]]
        if partition == "train" and session["case"] != "normal":
            partition = "excluded_train_faults"
        partitions[partition].append(session)
    if not partitions["train"]:
        raise ValueError("No normal training sessions in selected groups.")
    return {"split_version": "gate-group-split-1", "seed": seed,
            "group_assignments": assignments, "partitions": partitions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suites", type=Path, nargs="+")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = split_sessions(load_sessions(args.suites), seed=args.seed)
        result["code_version"] = code_version()
        result["source_suites"] = [str(p.resolve()) for p in args.suites]
        encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Split failed: {error}\n")
    print(f"Saved split plan: {args.output}")
    for name, sessions in result["partitions"].items():
        print(f"{name}: {len(sessions)} sessions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
