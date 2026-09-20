"""Read the collector's append-only SQLite history without creating a database."""

from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3

from contracts.telemetry import decode_telemetry


@contextmanager
def open_history(path):
    # A connection belongs to one request/thread. mode=ro also rejects missing files.
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")  # Consistent snapshot across queries in this request.
        yield db


def check_history(db):
    db.execute("""SELECT rowid, device_id, boot_id, sequence_number, device_timestamp,
        received_at, received_monotonic_ns, topic, payload FROM telemetry LIMIT 0""")


def record(row):
    return {
        "id": row["rowid"],
        "received_at": row["received_at"],
        "received_monotonic_ns": row["received_monotonic_ns"],
        "topic": row["topic"],
        "telemetry": decode_telemetry(row["payload"].encode("utf-8"), topic=row["topic"]),
    }


def device_summaries(db, *, after_device, limit):
    # The primary key starts with device_id; no fixed set of ESP32 node IDs.
    rows = db.execute("""SELECT device_id, COUNT(*) AS message_count, MAX(rowid) AS last_id
        FROM telemetry WHERE device_id > ? GROUP BY device_id
        ORDER BY device_id LIMIT ?""", (after_device, limit + 1)).fetchall()
    items = []
    for row in rows[:limit]:
        latest = db.execute("SELECT received_at FROM telemetry WHERE rowid=?", (row["last_id"],)).fetchone()
        items.append({"device_id": row["device_id"], "message_count": row["message_count"],
                      "last_received_at": latest["received_at"]})
    return {"items": items, "has_more": len(rows) > limit,
            "next_after_device": items[-1]["device_id"] if items else after_device}


def device_details(db, device_id):
    latest = db.execute("SELECT rowid, * FROM telemetry WHERE device_id=? ORDER BY rowid DESC LIMIT 1",
                        (device_id,)).fetchone()
    if latest is None:
        return None
    count = db.execute("SELECT COUNT(*) FROM telemetry WHERE device_id=?", (device_id,)).fetchone()[0]
    return {"device_id": device_id, "message_count": count, "latest": record(latest)}


def device_history(db, device_id, *, after_id, limit):
    if db.execute("SELECT 1 FROM telemetry WHERE device_id=? LIMIT 1", (device_id,)).fetchone() is None:
        return None
    rows = db.execute("""SELECT rowid, * FROM telemetry WHERE device_id=? AND rowid>?
        ORDER BY rowid LIMIT ?""", (device_id, after_id, limit + 1)).fetchall()
    items = [record(row) for row in rows[:limit]]
    return {"items": items, "has_more": len(rows) > limit,
            "next_after_id": items[-1]["id"] if items else after_id}


def recent_history(db, device_id, *, limit):
    rows = db.execute("""SELECT rowid, * FROM telemetry WHERE device_id=?
        ORDER BY rowid DESC LIMIT ?""", (device_id, limit + 1)).fetchall()
    if not rows:
        return None
    return {"items": [record(row) for row in reversed(rows[:limit])],
            "older_available": len(rows) > limit}
