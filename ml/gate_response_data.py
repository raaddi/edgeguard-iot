"""Validated response exports with role-lazy access to observable records."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re

import numpy as np

from ml.gate_feature_export import _decode
from ml.gate_features import FEATURE_VERSION, MAX_EVENTS, MAX_SAMPLES, SAMPLE_MS
from ml.gate_forecast_data import FEATURE_NAMES
from ml.gate_response_export import EXPORT_VERSION, HISTORICAL_SEEDS, MAX_SESSIONS
from ml.gate_response_targets import RESPONSE_VERSION, extract_response_examples
from ml.gate_sequences import TARGET_NAMES, iter_sequences
from simulator.gate import MODEL_VERSION
from simulator.gate_pilot import CASES, DATASET_VERSION
from simulator.gate_research_suite import CALIBRATION_CONDITIONS, CONDITIONS

ROLES = ("train", "selection", "calibration", "evaluation")
RESPONSE_TARGET_NAMES = ("ack", "contact")
MAX_FILE_BYTES = 4 * 1024 * 1024


def _read(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Response input exceeds 4 MiB.")
    return raw


def _json(raw):
    try:
        return _decode(raw)
    except (RecursionError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid response JSON.") from error


def _rows(raw, limit):
    lines = raw.splitlines()
    if len(lines) > limit:
        raise ValueError("Too many response records.")
    return [_json(line) for line in lines]


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _same_json(left, right):
    try:
        return (json.dumps(left, sort_keys=True, allow_nan=False)
                == json.dumps(right, sort_keys=True, allow_nan=False))
    except RecursionError as error:
        raise ValueError("Response JSON is nested too deeply.") from error


def _count(value, maximum):
    return type(value) is int and 0 <= value <= maximum


class ResponseDataset:
    """Validate metadata now; open a role's files only when sessions(role) runs.

    Ground truth is hashed as provenance, never decoded or returned. Neither
    roles, seeds nor fault names enter feature arrays. Each session's stored
    examples must exactly match a fresh causal extraction from its raw records.
    """

    def __init__(self, root):
        self.root = Path(root).resolve()
        raw = _read(self.root / "manifest.json")
        self.manifest_sha256 = hashlib.sha256(raw).hexdigest()
        self.manifest = _json(raw)
        try:
            self._validate_manifest()
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("Invalid response manifest fields.") from error
        for name, filename in (("protocol", "protocol.md"), ("report", "report.json")):
            path = (self.root / filename).resolve()
            if (not path.is_relative_to(self.root)
                    or hashlib.sha256(_read(path)).hexdigest() != self.manifest[name + "_sha256"]):
                raise ValueError(f"Response {name} provenance hash mismatch.")

    def _validate_manifest(self):
        m = self.manifest
        versions = {"status": "completed", "export_version": EXPORT_VERSION,
                    "response_version": RESPONSE_VERSION, "feature_version": FEATURE_VERSION,
                    "dataset_version": DATASET_VERSION, "simulator_model_version": MODEL_VERSION,
                    "session_settings_version": "gate-session-settings-1", "source": "synthetic",
                    "history_samples": 20, "sample_ms": SAMPLE_MS, "aggregate_window_ms": 1000}
        if any(m[key] != value for key, value in versions.items()):
            raise ValueError("Unsupported or incomplete response export.")
        if any(type(m[key]) is not int for key in ("history_samples", "sample_ms", "aggregate_window_ms")):
            raise ValueError("Invalid response timing metadata.")
        if (m["protocol_file"] != "protocol.md" or not _hash(m["protocol_sha256"])
                or not _hash(m["report_sha256"])
                or not _same_json(m["historical_seeds_excluded"], sorted(HISTORICAL_SEEDS))):
            raise ValueError("Invalid response protocol provenance.")
        normalized_conditions = json.loads(json.dumps({key: asdict(value)
                                                       for key, value in CONDITIONS.items()}))
        if not _same_json(m["conditions"], normalized_conditions) or set(m["seed_roles"]) != set(ROLES):
            raise ValueError("Response conditions or roles differ from the protocol.")
        seen = set()
        expected = set()
        assignments = {}
        for role in ROLES:
            seeds = m["seed_roles"][role]
            maximum = 8 if role == "selection" else 16
            if (not isinstance(seeds, list) or not 1 <= len(seeds) <= maximum
                    or any(type(seed) is not int or not 0 <= seed < 2**32 for seed in seeds)
                    or len(set(seeds)) != len(seeds)
                    or set(seeds) & (seen | HISTORICAL_SEEDS)):
                raise ValueError("Response seed roles overlap or contain invalid seeds.")
            seen.update(seeds)
            assignments.update({str(seed): role for seed in seeds})
            conditions = list(CONDITIONS) if role == "evaluation" else list(CALIBRATION_CONDITIONS)
            cases = list(CASES) if role == "evaluation" else ["normal"]
            if m["role_conditions"][role] != conditions or m["role_cases"][role] != cases:
                raise ValueError("Response roles contain unexpected conditions or cases.")
            expected.update((role, seed, condition, case)
                            for seed in seeds for condition in conditions for case in cases)
        if (set(m["role_conditions"]) != set(ROLES) or set(m["role_cases"]) != set(ROLES)
                or m["group_assignments"] != assignments):
            raise ValueError("Response group assignments do not match seed roles.")
        sessions = m["sessions"]
        if (not isinstance(sessions, list) or not 1 <= len(sessions) <= MAX_SESSIONS
                or not _count(m["expected_sessions"], MAX_SESSIONS)
                or len(sessions) != m["expected_sessions"] or len(sessions) != len(expected)):
            raise ValueError("Invalid response session counts.")
        actual, run_ids = set(), set()
        self.entries = {role: [] for role in ROLES}
        for entry in sessions:
            role, seed, condition, case = (entry[k] for k in ("role", "seed", "condition", "case"))
            if type(seed) is not int or (role, seed, condition, case) not in expected:
                raise ValueError("Session is outside its frozen response role.")
            key = (role, seed, condition, case)
            run_id = f"response-v1-{role}-{condition}-{seed}-{case}"
            if (key in actual or entry["run_id"] != run_id or run_id in run_ids
                    or entry["paired_group"] != f"gate-v1-seed-{seed}"):
                raise ValueError("Duplicate or inconsistent response session identity.")
            actual.add(key)
            run_ids.add(run_id)
            if (any(not _count(entry[k], 64) for k in ("commands", "examples", "excluded"))
                    or entry["commands"] != len(CONDITIONS[condition].schedule)
                    or entry["commands"] != entry["examples"] + entry["excluded"]):
                raise ValueError("Invalid response session example counts.")
            for name in ("observations", "events", "ground_truth", "examples"):
                relative = (f"examples/{role}/{run_id}.json" if name == "examples"
                            else f"raw/{role}/{run_id}/{name}.{'json' if name == 'ground_truth' else 'jsonl'}")
                if entry[name + "_file"] != relative or not _hash(entry[name + "_sha256"]):
                    raise ValueError("Unsafe response path or invalid recorded hash.")
            self.entries[role].append(entry)
        if actual != expected:
            raise ValueError("Response sessions differ from their seed/condition/case grid.")
        for key in ("commands", "examples", "excluded"):
            if not _count(m[key], MAX_SESSIONS * 64) or m[key] != sum(s[key] for s in sessions):
                raise ValueError("Response totals do not match sessions.")

    def _session_bytes(self, entry, name):
        path = (self.root / entry[name + "_file"]).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Response file escapes the artifact root.")
        raw = _read(path)
        if hashlib.sha256(raw).hexdigest() != entry[name + "_sha256"]:
            raise ValueError(f"Response {name} hash mismatch.")
        return raw

    def sessions(self, role):
        if role not in ROLES:
            raise ValueError("Invalid response role.")
        for entry in sorted(self.entries[role], key=lambda e: (e["seed"], e["condition"], e["case"])):
            observations = _rows(self._session_bytes(entry, "observations"), MAX_SAMPLES)
            events = _rows(self._session_bytes(entry, "events"), MAX_EVENTS)
            data = _json(self._session_bytes(entry, "examples"))
            self._session_bytes(entry, "ground_truth")
            if (not observations or any(not isinstance(row, dict) or row.get("run_id") != entry["run_id"]
                                        for row in observations)):
                raise ValueError("Raw observations do not match response session identity.")
            settings = CONDITIONS[entry["condition"]]
            if [row.get("logical_ms") for row in observations] != list(range(0, settings.duration_ms + 1, SAMPLE_MS)):
                raise ValueError("Raw response timing differs from its frozen condition.")
            expected = extract_response_examples(observations, events, history_samples=20)
            schedule = [(event["logical_ms"], event["message"]["value"])
                        for event in events if event["kind"] == "command_sent"]
            if schedule != list(settings.schedule):
                raise ValueError("Raw response commands differ from their frozen condition.")
            if not _same_json(data, expected):
                raise ValueError("Stored response examples differ from causal raw extraction.")
            commands = sum(event["kind"] == "command_sent" for event in events)
            if (commands != entry["commands"] or len(data["examples"]) != entry["examples"]
                    or len(data["excluded"]) != entry["excluded"]):
                raise ValueError("Raw response counts differ from recorded metadata.")
            yield entry, observations, events, data


def _inputs(rows):
    return [[np.nan if row[name] is None else row[name] for name in FEATURE_NAMES] for row in rows]


def response_arrays(sessions):
    """Convert validated session batches; censored durations remain NaN."""
    xs, ys, follow_up = [], [], []
    for _, _, _, data in sessions:
        for row in data["examples"]:
            xs.append(_inputs(row["x"]))
            ys.append([np.nan if row["y"][name]["duration_ms"] is None
                       else row["y"][name]["duration_ms"] for name in RESPONSE_TARGET_NAMES])
            follow_up.append([row["y"][name]["follow_up_ms"] for name in RESPONSE_TARGET_NAMES])
    return (np.asarray(xs, dtype=np.float32).reshape(-1, 20, len(FEATURE_NAMES)),
            np.asarray(ys, dtype=np.float32).reshape(-1, 2),
            np.asarray(follow_up, dtype=np.float32).reshape(-1, 2))


def sensor_arrays(sessions):
    """Derive matching normal-group histories with next-sample sensor targets."""
    xs, ys = [], []
    for _, observations, events, _ in sessions:
        for row in iter_sequences(observations, events, history_samples=20, horizon_samples=1):
            xs.append(_inputs(row["x"]))
            ys.append([np.nan if row["y"][name] is None else float(row["y"][name])
                       for name in TARGET_NAMES])
    return (np.asarray(xs, dtype=np.float32).reshape(-1, 20, len(FEATURE_NAMES)),
            np.asarray(ys, dtype=np.float32).reshape(-1, 3))
