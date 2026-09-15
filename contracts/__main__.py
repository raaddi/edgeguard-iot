"""Validate a JSON Lines telemetry file (or stdin) without hardware or MQTT."""

import argparse
from contextlib import nullcontext
import sys

from contracts.telemetry import MAX_PAYLOAD_BYTES, TelemetryError, decode_telemetry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default="-", help="JSONL file, or - for stdin")
    args = parser.parse_args()
    line_number = 0
    try:
        with (nullcontext(sys.stdin.buffer) if args.path == "-" else open(args.path, "rb")) as stream:
            while line := stream.readline(MAX_PAYLOAD_BYTES + 1):
                line_number += 1
                decode_telemetry(line)
        if not line_number:
            raise TelemetryError("No telemetry messages found.")
    except (OSError, TelemetryError) as error:
        print(f"Validation failed at line {line_number}: {error}", file=sys.stderr)
        return 1
    print(f"Validated {line_number} telemetry messages (schema 1.0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
