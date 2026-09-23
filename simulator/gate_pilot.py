"""Offline observability pilot. No hardware, MQTT, wall-clock waits or trained ML."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import random
from uuid import NAMESPACE_URL, uuid4, uuid5

from contracts.commands import target_rejection, validate_command, validate_result
from simulator.__main__ import code_version, identifier
from simulator.gate import Gate, GateConfig, MODEL_VERSION

CASES = ("normal", "command_delay", "motion_stall", "open_contact_stuck_low")
DATASET_VERSION = "gate-pilot-0.1"
SAMPLE_MS = 50
DURATION_MS = 8000
SCHEDULE = ((1000, 110), (5000, 0))
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "experiments" / "runs"


def simulate_session(*, seed, case, run_id, device_id="virtual_gate_01",
                     feedback_device_id="virtual_gate_01", measure_current=True):
    """Paired seeds share nominal parameters. Returned truth is never a feature."""
    if case not in CASES:
        raise ValueError("Unknown gate case.")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be in 0..2**32-1.")
    for value in (run_id, device_id, feedback_device_id):
        identifier(value)
    rng = random.Random(seed)
    config = GateConfig(
        stroke_ms=rng.randrange(900, 1301, 50),
        motion_stall=case == "motion_stall",
        open_contact_stuck_low=case == "open_contact_stuck_low",
        measure_current=measure_current,
    )
    nominal_delay = rng.choice((50, 100, 150))
    delay = 1200 if case == "command_delay" else nominal_delay
    gate = Gate(config, seed=seed)
    boot = str(uuid5(NAMESPACE_URL, f"{run_id}/{device_id}"))
    feedback_boot = str(uuid5(NAMESPACE_URL, f"{run_id}/{feedback_device_id}"))
    pending, events, observations = [], [], []
    for now in range(0, DURATION_MS + 1, SAMPLE_MS):
        if now:
            gate.advance(SAMPLE_MS)
        for sent_ms, target in SCHEDULE:
            if now != sent_ms:
                continue
            command = {
                "schema_version": "1.0",
                "command_id": str(uuid5(NAMESPACE_URL, f"{run_id}/command/{now}")),
                "device_id": device_id, "target_boot_id": boot,
                "component_id": "servo_01", "operation": "set", "value": target,
                "observed_uptime_ms": now, "expires_uptime_ms": now + 3000,
            }
            validate_command(command)
            events.append({"logical_ms": now, "kind": "command_sent", "message": command})
            pending.append((now + delay, command))
        while pending and pending[0][0] <= now:
            _, command = pending.pop(0)
            reason = target_rejection(
                command, device_id=device_id, boot_id=boot, uptime_ms=now,
                capabilities={"servo_01": {"kind": "servo", "allowed_values": [0, 110]}},
            )
            if reason is None:
                gate.command(command["value"])
            result = {
                "schema_version": "1.0", "command_id": command["command_id"],
                "device_id": device_id, "boot_id": boot, "component_id": "servo_01",
                "status": "accepted" if reason is None else "rejected", "reason": reason,
                "handled_uptime_ms": now,
            }
            validate_result(result)
            events.append({"logical_ms": now, "kind": "command_result", "message": result})
        observations.append({
            "schema_version": DATASET_VERSION, "run_id": run_id,
            "device_id": feedback_device_id, "boot_id": feedback_boot,
            "mechanism_id": "gate_01", "sequence_number": now // SAMPLE_MS,
            "logical_ms": now, **asdict(gate.read()),
        })
    truth = {
        "case": case, "seed": seed, "paired_group": f"gate-v1-seed-{seed}",
        "config": asdict(config), "delivery_delay_ms": delay,
        "label_scope": "configured session condition; not event onset intervals",
    }
    return observations, events, truth


def summarize(observations, events):
    """Only observable data is used; these are measurements, not ML diagnoses."""
    sent = {e["message"]["command_id"]: e["logical_ms"]
            for e in events if e["kind"] == "command_sent"}
    delays = [e["logical_ms"] - sent[e["message"]["command_id"]]
              for e in events if e["kind"] == "command_result"]
    currents = [o["current_a"] for o in observations if o["current_a"] is not None]
    return {
        "result_delays_ms": delays,
        "open_contact_seen_before_close": any(o["open_contact"] for o in observations
                                              if 1000 <= o["logical_ms"] < 5000),
        "peak_current_a": max(currents) if currents else None,
        "final_closed_contact": observations[-1]["closed_contact"],
    }


def _json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _jsonl(path, rows):
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, allow_nan=False) + "\n")


def run_suite(*, output=DEFAULT_OUTPUT, suite_id=None, seed=42, sessions_per_case=3,
              device_id="virtual_gate_01", feedback_device_id="virtual_gate_01",
              measure_current=True):
    if type(sessions_per_case) is not int or not 1 <= sessions_per_case <= 25:
        raise ValueError("sessions_per_case must be in 1..25.")
    if type(seed) is not int or not 0 <= seed <= 2**32 - sessions_per_case:
        raise ValueError("Seed range would be invalid.")
    for value in (device_id, feedback_device_id):
        identifier(value)
    if type(measure_current) is not bool:
        raise ValueError("measure_current must be boolean.")
    suite_id = str(uuid4()) if suite_id is None else identifier(suite_id)
    root = Path(output) / suite_id
    root.mkdir(parents=True, exist_ok=False)
    manifest = {
        "dataset_version": DATASET_VERSION, "source": "synthetic",
        "model_version": MODEL_VERSION, "suite_id": suite_id, "status": "running",
        "code_version": code_version(), "python_version": platform.python_version(),
        "seed": seed, "sessions_per_case": sessions_per_case,
        "device_id": device_id, "feedback_device_id": feedback_device_id,
        "measure_current": measure_current, "sample_ms": SAMPLE_MS,
        "duration_ms": DURATION_MS, "schedule_ms_degrees": SCHEDULE, "sessions": [],
    }
    _json(root / "manifest.json", manifest)
    try:
        for index in range(sessions_per_case):
            for case in CASES:
                run_id = str(uuid5(NAMESPACE_URL, f"{suite_id}/{index}/{case}"))
                folder = root / run_id
                folder.mkdir()
                observations, events, truth = simulate_session(
                    seed=seed + index, case=case, run_id=run_id, device_id=device_id,
                    feedback_device_id=feedback_device_id, measure_current=measure_current,
                )
                _jsonl(folder / "observations.jsonl", observations)
                _jsonl(folder / "events.jsonl", events)
                _json(folder / "ground_truth.json", truth)
                summary = summarize(observations, events)
                _json(folder / "summary.json", summary)
                manifest["sessions"].append({"run_id": run_id, "samples": len(observations)})
        manifest["status"] = "completed"
    except BaseException:
        manifest["status"] = "failed"
        raise
    finally:
        _json(root / "manifest.json", manifest)
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sessions-per-case", type=int, default=3)
    parser.add_argument("--suite-id", type=identifier)
    parser.add_argument("--device-id", type=identifier, default="virtual_gate_01")
    parser.add_argument("--feedback-device-id", type=identifier, default="virtual_gate_01")
    parser.add_argument("--without-current", action="store_true")
    args = parser.parse_args()
    try:
        root = run_suite(suite_id=args.suite_id, seed=args.seed,
                         sessions_per_case=args.sessions_per_case, device_id=args.device_id,
                         feedback_device_id=args.feedback_device_id,
                         measure_current=not args.without_current)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Pilot failed: {error}\n")
    print(f"Synthetic pilot completed: {root}")
    print(f"{4 * args.sessions_per_case} sessions, 161 samples/session; no trained ML.")
    print("case                       result delay [ms]   open seen   peak current [A]")
    for session in json.loads((root / "manifest.json").read_text())["sessions"]:
        folder = root / session["run_id"]
        truth = json.loads((folder / "ground_truth.json").read_text())
        summary = json.loads((folder / "summary.json").read_text())
        print(f"{truth['case']:26} {str(summary['result_delays_ms']):19} "
              f"{str(summary['open_contact_seen_before_close']):11} {summary['peak_current_a']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
