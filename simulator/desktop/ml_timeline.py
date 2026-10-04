"""Bounded read-only adapter for saved research timelines; no model loading."""

import json
import math
from pathlib import Path

MAX_BYTES = 4 * 1024 * 1024
METHODS = ("gru", "persistence", "isolation_forest", "temporal_rules")


def validate_timeline(data):
    def fail():
        raise ValueError("Nieprawidłowa oś czasu ML: oczekiwane zgodne serie i skończone liczby.")
    if not isinstance(data, dict) or data.get("timeline_version") not in (None, "gate-ml-view-1"):
        fail()
    times = data.get("logical_ms")
    if (not isinstance(times, list) or not 2 <= len(times) <= 10000
            or any(type(t) is not int or not 0 <= t <= 500000 or t % 50 for t in times)
            or any(a >= b for a, b in zip(times, times[1:]))):
        fail()
    size = len(times)
    def number(v):
        return v is None or type(v) in (int, float) and abs(v) <= 1e6 and math.isfinite(v)
    def series(values, boolean=False):
        if not isinstance(values, list) or len(values) != size:
            fail()
        if any(type(v) is not bool if boolean else not number(v) for v in values):
            fail()
        return values
    for key in ("actual", "predicted", "scaled_residuals"):
        matrix = data.get(key)
        if (not isinstance(matrix, list) or len(matrix) != size
                or any(not isinstance(r, list) or len(r) != 3 or any(not number(v) for v in r) for r in matrix)):
            fail()
        if key != "scaled_residuals":
            for row in matrix:
                if any(v is not None and (v not in (0, 1) if key == "actual" else not 0 <= v <= 1) for v in row[:2]):
                    fail()
    pending = series(data.get("pending_commands"))
    if any(type(v) is not int or not 0 <= v <= 1000 for v in pending):
        fail()
    labels = series(data.get("labels"), boolean=True)
    scores = data.get("scores")
    scores = {"gru": scores} if isinstance(scores, list) else scores
    if not isinstance(scores, dict) or "gru" not in scores or not set(scores) <= set(METHODS):
        fail()
    thresholds = data.get("thresholds", {"gru": data.get("threshold")})
    flags = data.get("method_alarms", {"gru": data.get("alarms")})
    if not isinstance(thresholds, dict) or not isinstance(flags, dict):
        fail()
    for method, values in scores.items():
        series(values)
        series(flags.get(method), boolean=True)
        threshold = thresholds.get(method)
        if threshold is None or not number(threshold):
            fail()
    commands = data.get("commands")
    if not isinstance(commands, list) or len(commands) > 1000:
        fail()
    sent = []
    for event in commands:
        if not isinstance(event, dict):
            fail()
        if "kind" in event and event["kind"] != "command_sent":
            continue
        now = event.get("logical_ms")
        value = event.get("value", event.get("message", {}).get("value"))
        if type(now) is not int or not 0 <= now <= times[-1] or now % 50 or type(value) is not int or value not in (0, 110):
            fail()
        sent.append({"logical_ms": now, "value": value})
    for key in ("run_id", "case", "condition", "profile", "policy", "source", "model_version", "feature_version"):
        if key in data and (not isinstance(data[key], str) or not 1 <= len(data[key]) <= 160):
            fail()
    if not data.get("run_id"):
        fail()
    return {**data, "scores": scores, "thresholds": thresholds, "method_alarms": flags,
            "labels": labels, "commands": sorted(sent, key=lambda e: e["logical_ms"])}


def read_timeline(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Plik przekracza limit 4 MiB dla jednej osi czasu.")
    return validate_timeline(json.loads(raw.decode("utf-8-sig")))
