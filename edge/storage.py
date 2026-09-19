"""Validated telemetry in SQLite; duplicate identities cannot overwrite history."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time

from contracts.telemetry import decode_telemetry


class TelemetryStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=2)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS telemetry (
            device_id TEXT NOT NULL, boot_id TEXT NOT NULL, sequence_number INTEGER NOT NULL,
            device_timestamp TEXT, received_at TEXT NOT NULL, received_monotonic_ns INTEGER NOT NULL,
            topic TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(device_id, boot_id, sequence_number))""")
        self.db.commit()

    def ingest(self, topic, payload, *, received_at=None, received_monotonic_ns=None):
        message = decode_telemetry(payload, topic=topic)
        canonical = json.dumps(message, sort_keys=True, separators=(",", ":"), allow_nan=False)
        identity = (message["device_id"], message["boot_id"], message["sequence_number"])
        with self.db:
            inserted = self.db.execute(
                "INSERT INTO telemetry VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(device_id, boot_id, sequence_number) DO NOTHING",
                (*identity, message["timestamp"],
                 received_at or datetime.now(timezone.utc).isoformat(),
                 time.monotonic_ns() if received_monotonic_ns is None else received_monotonic_ns,
                 topic, canonical),
            ).rowcount
            if inserted:
                return "stored"
            previous = self.db.execute(
                "SELECT payload FROM telemetry WHERE device_id=? AND boot_id=? AND sequence_number=?",
                identity,
            ).fetchone()[0]
            return "duplicate" if previous == canonical else "conflict"

    def close(self):
        self.db.close()
