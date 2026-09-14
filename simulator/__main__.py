"""Print telemetry as JSON Lines; write separate run metadata to stderr."""

import argparse
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

from simulator.normal_activity import gas_signal
from simulator.telemetry import SENSOR_ID, START, build_message, session_id


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise argparse.ArgumentTypeError("Use 1-64 letters, digits, underscores or hyphens.")
    return value


def sample_count(value: str) -> int:
    count = int(value)
    if not 1 <= count <= 100_000:
        raise argparse.ArgumentTypeError("Samples must be between 1 and 100000.")
    return count


def code_version() -> dict:
    root = Path(__file__).resolve().parents[1]
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.DEVNULL,
            text=True, timeout=5,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, stderr=subprocess.DEVNULL,
            text=True, timeout=5,
        )
        return {"commit": revision, "working_tree_dirty": bool(status.strip())}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "working_tree_dirty": None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--samples", type=sample_count, default=5)
    parser.add_argument("--device-id", type=identifier, default="virtual_node_01")
    parser.add_argument("--run-id", type=identifier, default="lesson-01")
    args = parser.parse_args()

    # Logical time does not depend on when or how quickly the program runs.
    start = START
    interval_seconds = 1
    sensor_id = SENSOR_ID
    boot_id = session_id(args.run_id, args.device_id)
    manifest = {
        "run_id": args.run_id,
        "source": "synthetic",
        "generator": "illustrative-gas-v1",
        "seed": args.seed,
        "samples": args.samples,
        "device_id": args.device_id,
        "boot_id": boot_id,
        "sensor_id": sensor_id,
        "logical_start": start.isoformat(),
        "interval_seconds": interval_seconds,
        "scenario_schedule": [],
        "code_version": code_version(),
        "python_version": platform.python_version(),
    }
    print(json.dumps(manifest), file=sys.stderr)

    signal = gas_signal(args.seed)
    for sequence in range(args.samples):
        message = build_message(args.device_id, boot_id, sequence, next(signal))
        print(json.dumps(message))


if __name__ == "__main__":
    main()
