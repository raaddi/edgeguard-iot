"""Export per-session causal features from a frozen pilot split plan."""

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from ml.gate_features import FEATURE_VERSION, MAX_EVENTS, MAX_SAMPLES, extract_features
from ml.gate_split import split_sessions
from simulator.__main__ import code_version
from simulator.gate_pilot import CASES, PROFILES

MAX_FILE_BYTES = 8 * 1024 * 1024


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key.")
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def _decode(raw):
    return json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)


def _read(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Pilot input exceeds 8 MiB.")
    return raw


def _rows(raw, limit):
    lines = raw.splitlines()
    if len(lines) > limit:
        raise ValueError("Too many pilot records.")
    return [_decode(line) for line in lines]


def validate_plan(plan):
    if plan["split_version"] != "gate-group-split-1":
        raise ValueError("Unsupported split version.")
    names = {"train", "validation", "test", "excluded_train_faults"}
    if set(plan["partitions"]) != names:
        raise ValueError("Invalid split partitions.")
    sessions = [s for rows in plan["partitions"].values() for s in rows]
    if not 1 <= len(sessions) <= 1000:
        raise ValueError("Expected 1..1000 pilot sessions.")
    for session in sessions:
        if (set(session) != {"run_id", "path", "paired_group", "case", "profile"}
                or str(UUID(session["run_id"])) != session["run_id"]
                or not isinstance(session["path"], str)
                or not Path(session["path"]).is_absolute()
                or not isinstance(session["paired_group"], str)
                or session["case"] not in CASES or session["profile"] not in PROFILES):
            raise ValueError("Invalid split session metadata.")
    expected = split_sessions(sessions, seed=plan["seed"])
    if any(plan[key] != expected[key] for key in ("group_assignments", "partitions")):
        raise ValueError("Split no longer matches its grouped assignment policy.")


def export_features(split_path, output, *, window_ms=1000):
    split_bytes = _read(split_path)
    plan = _decode(split_bytes)
    validate_plan(plan)
    if type(window_ms) is not int or not 50 <= window_ms <= 60_000 or window_ms % 50:
        raise ValueError("Invalid feature window.")
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    manifest = {"feature_version": FEATURE_VERSION, "status": "running",
                "window_ms": window_ms, "code_version": code_version(),
                "split_sha256": hashlib.sha256(split_bytes).hexdigest(),
                "excluded_sessions": len(plan["partitions"]["excluded_train_faults"]),
                "sessions": [], "feature_names": []}

    def save_manifest():
        (root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    save_manifest()
    try:
        # Preserve the exact plan as provenance; it is not a feature file.
        (root / "source-split.json").write_bytes(split_bytes)
        for partition in ("train", "validation", "test"):
            folder = root / partition
            folder.mkdir()
            for session in plan["partitions"][partition]:
                source = Path(session["path"])
                obs_bytes = _read(source / "observations.jsonl")
                event_bytes = _read(source / "events.jsonl")
                observations = _rows(obs_bytes, MAX_SAMPLES)
                events = _rows(event_bytes, MAX_EVENTS)
                features = extract_features(observations, events, window_ms=window_ms)
                if observations[0]["run_id"] != session["run_id"]:
                    raise ValueError("Observation session does not match split plan.")
                names = list(features[0]["x"])
                if manifest["feature_names"] and manifest["feature_names"] != names:
                    raise ValueError("Feature order changed between sessions.")
                manifest["feature_names"] = names
                target = folder / (session["run_id"] + ".jsonl")
                with target.open("x", encoding="utf-8") as stream:
                    for row in features:
                        stream.write(json.dumps(row, allow_nan=False) + "\n")
                manifest["sessions"].append({
                    "run_id": session["run_id"], "partition": partition, "rows": len(features),
                    "observations_sha256": hashlib.sha256(obs_bytes).hexdigest(),
                    "events_sha256": hashlib.sha256(event_bytes).hexdigest(),
                })
        manifest["status"] = "completed"
    except BaseException:
        manifest["status"] = "failed"
        raise
    finally:
        save_manifest()
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window-ms", type=int, default=1000)
    args = parser.parse_args()
    try:
        manifest = export_features(args.split, args.output, window_ms=args.window_ms)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"Feature export failed: {error}\n")
    print(f"Saved {len(manifest['feature_names'])} features to {args.output}")
    print(f"Sessions: {len(manifest['sessions'])}; rows: {sum(s['rows'] for s in manifest['sessions'])}")
    print("No trained model; null values preserved; excluded training faults not exported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
