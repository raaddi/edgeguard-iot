"""Command wire contracts and target checks; no MQTT or actuator side effects."""

import argparse
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, ValidationError

MAX_COMMAND_BYTES = 4096
MAX_VALIDITY_MS = 60_000
MAX_UPTIME_MS = 9007199254740991
_ROOT = Path(__file__).parent
_COMMAND_SCHEMA = json.loads((_ROOT / "command-v1.schema.json").read_text(encoding="utf-8"))
_RESULT_SCHEMA = json.loads((_ROOT / "command-result-v1.schema.json").read_text(encoding="utf-8"))
for _schema in (_COMMAND_SCHEMA, _RESULT_SCHEMA):
    Draft202012Validator.check_schema(_schema)
_COMMAND = Draft202012Validator(_COMMAND_SCHEMA)
_RESULT = Draft202012Validator(_RESULT_SCHEMA)


class CommandError(ValueError):
    """Malformed or incompatible command/result; not an actuator rejection."""


def _topic(device_id, suffix):
    if not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device_id):
        raise CommandError("Invalid device identifier.")
    return f"edgeguard/devices/{device_id}/{suffix}"


def command_topic(device_id):
    return _topic(device_id, "commands")


def result_topic(device_id):
    return _topic(device_id, "command-results")


def _validate(message, validator, topic, suffix):
    try:
        encoded = json.dumps(message, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_COMMAND_BYTES:
            raise CommandError("Command/result exceeds 4096 bytes.")
        validator.validate(message)
    except ValidationError as error:
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        raise CommandError(f"{location}: {error.message}") from error
    except (TypeError, ValueError, RecursionError) as error:
        raise CommandError(str(error)) from error
    if topic is not None and topic != _topic(message["device_id"], suffix):
        raise CommandError("Topic and device identifier do not match.")


def validate_command(message, *, topic=None):
    _validate(message, _COMMAND, topic, "commands")
    validity = message["expires_uptime_ms"] - message["observed_uptime_ms"]
    if not 0 < validity <= MAX_VALIDITY_MS:
        raise CommandError("Validity must be greater than 0 and at most 60000 ms.")


def validate_result(message, *, topic=None):
    _validate(message, _RESULT, topic, "command-results")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CommandError("Duplicate JSON key.")
        result[key] = value
    return result


def _nonfinite(value):
    raise CommandError("Non-finite JSON number.")


def _decode(payload, validate, topic):
    if not isinstance(payload, bytes) or len(payload) > MAX_COMMAND_BYTES:
        raise CommandError("Expected at most 4096 bytes.")
    try:
        message = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise CommandError(f"Invalid JSON: {error}") from error
    validate(message, topic=topic)
    return message


def decode_command(payload, *, topic=None):
    return _decode(payload, validate_command, topic)


def decode_result(payload, *, topic=None):
    return _decode(payload, validate_result, topic)


def target_rejection(command, *, device_id, boot_id, uptime_ms, capabilities):
    """Return a rejection reason or None. None does NOT execute/acknowledge anything.

    capabilities maps local component IDs to kind and allowed_values; it comes
    from trusted node configuration, never from the received command.
    """
    validate_command(command)
    if type(uptime_ms) is not int or not 0 <= uptime_ms <= MAX_UPTIME_MS:
        raise ValueError("Invalid local uptime.")
    if command["device_id"] != device_id:
        return "wrong_device"
    if command["target_boot_id"] != boot_id:
        return "wrong_boot"
    if uptime_ms < command["observed_uptime_ms"]:
        return "not_yet_valid"
    if uptime_ms >= command["expires_uptime_ms"]:
        return "expired"
    component = capabilities.get(command["component_id"])
    if component is None:
        return "unknown_component"
    if component["kind"] not in {"fan", "light", "servo"}:
        return "unsupported_operation"
    if command["operation"] == "auto":
        return None if component["kind"] == "fan" else "unsupported_operation"
    if command["value"] not in component["allowed_values"]:
        return "value_out_of_range"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--result", action="store_true", help="Validate a command result instead")
    parser.add_argument("--topic", help="Also verify MQTT topic and device identity")
    args = parser.parse_args()
    try:
        with args.file.open("rb") as source:
            payload = source.read(MAX_COMMAND_BYTES + 1)
        decoder = decode_result if args.result else decode_command
        decoder(payload, topic=args.topic)
    except (OSError, CommandError) as error:
        print(f"Rejected: {error}")
        return 1
    print("Validated result 1.0." if args.result else "Validated command 1.0 (format only; not sent or executed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
