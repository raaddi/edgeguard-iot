"""Single-sensor exercise using the shared telemetry contract."""

from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from contracts.telemetry import build_telemetry

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
SENSOR_ID = "gas_01"


def session_id(run_id: str, device_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"edgeguard:{run_id}:{device_id}"))


def build_message(device_id: str, boot_id: str, sequence: int, value: float) -> dict:
    return build_telemetry(
        device_id=device_id, boot_id=boot_id, sequence_number=sequence,
        timestamp=(START + timedelta(seconds=sequence)).isoformat(), uptime_ms=sequence * 1000,
        sensors={
            SENSOR_ID: {"measurement": "gas_signal", "unit": "normalized", "status": "ok", "value": value},
        },
    )
