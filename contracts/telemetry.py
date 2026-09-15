"""Validate JSON telemetry before transport/storage; no network calls."""

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

SCHEMA_VERSION = "1.0"
MAX_PAYLOAD_BYTES = 32 * 1024
_SCHEMA = json.loads(Path(__file__).with_name("telemetry-v1.schema.json").read_text(encoding="utf-8"))
_FORMATS = FormatChecker()


@_FORMATS.checks("date-time", raises=ValueError)
def _valid_datetime(value):
    # The schema restricts the syntax to UTC. Check calendar validity as well,
    # without optional format packages or accepting Python's relaxed ISO syntax.
    if isinstance(value, str):
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    return True


Draft202012Validator.check_schema(_SCHEMA)
_VALIDATOR = Draft202012Validator(_SCHEMA, format_checker=_FORMATS)


class TelemetryError(ValueError):
    """Rejected payload; callers decide how to count/report it."""


def telemetry_topic(device_id: str) -> str:
    if not isinstance(device_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device_id):
        raise TelemetryError("Invalid device identifier.")
    return f"edgeguard/devices/{device_id}/telemetry"


def validate_telemetry(message: dict, *, topic: str | None = None) -> None:
    """Check schema, finite JSON values, size and optional MQTT topic identity."""
    try:
        encoded = json.dumps(message, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_PAYLOAD_BYTES:
            raise TelemetryError("Telemetry exceeds 32768 bytes.")
        _VALIDATOR.validate(message)
    except ValidationError as error:
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        raise TelemetryError(f"{location}: {error.message}") from error
    except (TypeError, ValueError, RecursionError) as error:
        raise TelemetryError(str(error)) from error
    if set(message["sensors"]) & set(message["actuators"]):
        raise TelemetryError("Sensor and actuator identifiers must be distinct within a node.")
    if topic is not None and topic != telemetry_topic(message["device_id"]):
        raise TelemetryError("Topic and payload device identifiers do not match.")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TelemetryError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise TelemetryError(f"Non-finite JSON number: {value}")


def decode_telemetry(payload: bytes, *, topic: str | None = None) -> dict:
    """Strict UTF-8 JSON decoding with a size bound before parsing."""
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise TelemetryError("Telemetry exceeds 32768 bytes.")
    try:
        message = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object,
                             parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise TelemetryError(f"Invalid JSON: {error}") from error
    validate_telemetry(message, topic=topic)
    return message


def build_telemetry(*, device_id, boot_id, sequence_number, timestamp, uptime_ms,
                    sensors, actuators=None) -> dict:
    """Build an owned snapshot; never share mutable state with the producer."""
    message = {
        "schema_version": SCHEMA_VERSION, "device_id": device_id, "boot_id": boot_id,
        "sequence_number": sequence_number, "timestamp": timestamp, "uptime_ms": uptime_ms,
        "sensors": deepcopy(sensors), "actuators": deepcopy(actuators if actuators is not None else {}),
    }
    validate_telemetry(message)
    return message
