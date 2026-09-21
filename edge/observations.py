"""Append-only command/result receipts, distinct from actuator execution history."""

import json

from contracts.commands import CommandError, decode_command, decode_result


def decode_control(topic, payload):
    if topic.endswith("/commands"):
        return "command", decode_command(payload, topic=topic)
    if topic.endswith("/command-results"):
        return "result", decode_result(payload, topic=topic)
    raise CommandError("Not a command/result topic")


def initialize_observations(db):
    db.execute("""CREATE TABLE IF NOT EXISTS control_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CHECK(kind IN ('command', 'result')),
        device_id TEXT NOT NULL, command_id TEXT NOT NULL,
        message_boot_id TEXT NOT NULL, component_id TEXT NOT NULL,
        collector_session_id TEXT NOT NULL,
        received_at TEXT NOT NULL, received_monotonic_ns INTEGER NOT NULL,
        mqtt_qos INTEGER NOT NULL CHECK(mqtt_qos BETWEEN 0 AND 2),
        mqtt_duplicate INTEGER NOT NULL CHECK(mqtt_duplicate IN (0, 1)),
        topic TEXT NOT NULL, payload TEXT NOT NULL)""")
    db.execute("""CREATE INDEX IF NOT EXISTS control_device_order
        ON control_observations(device_id, id)""")
    db.execute("""CREATE INDEX IF NOT EXISTS control_command_order
        ON control_observations(device_id, command_id, id)""")


def append_observation(db, topic, payload, *, collector_session_id, received_at,
                       received_monotonic_ns, mqtt_qos, mqtt_duplicate):
    kind, message = decode_control(topic, payload)
    if type(mqtt_qos) is not int or mqtt_qos not in (0, 1, 2) or type(mqtt_duplicate) is not bool:
        raise ValueError("Invalid local MQTT receipt metadata")
    canonical = json.dumps(message, sort_keys=True, separators=(",", ":"), allow_nan=False)
    boot = message["target_boot_id"] if kind == "command" else message["boot_id"]
    # Repeated deliveries and conflicting content are observations, not overwrites.
    with db:
        cursor = db.execute("""INSERT INTO control_observations
            (kind, device_id, command_id, message_boot_id, component_id,
             collector_session_id, received_at, received_monotonic_ns,
             mqtt_qos, mqtt_duplicate, topic, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (kind, message["device_id"], message["command_id"], boot, message["component_id"],
             collector_session_id, received_at, received_monotonic_ns,
             mqtt_qos, int(mqtt_duplicate), topic, canonical))
        observation_id = cursor.lastrowid
    return observation_id


def control_record(row):
    kind, message = decode_control(row["topic"], row["payload"].encode("utf-8"))
    boot = message["target_boot_id"] if kind == "command" else message["boot_id"]
    if (kind != row["kind"] or message["device_id"] != row["device_id"]
            or message["command_id"] != row["command_id"]
            or boot != row["message_boot_id"] or message["component_id"] != row["component_id"]):
        raise CommandError("Control observation index and payload do not match")
    return {"id": row["id"], "kind": kind, "received_at": row["received_at"],
            "received_monotonic_ns": row["received_monotonic_ns"],
            "collector_session_id": row["collector_session_id"],
            "mqtt_qos": row["mqtt_qos"], "mqtt_duplicate": bool(row["mqtt_duplicate"]),
            "topic": row["topic"], "message": message}


def control_history(db, device_id, *, after_id, limit, command_id=None):
    query = "SELECT * FROM control_observations WHERE device_id=? AND id>?"
    params = [device_id, after_id]
    if command_id is not None:
        query += " AND command_id=?"
        params.append(command_id)
    rows = db.execute(query + " ORDER BY id LIMIT ?", (*params, limit + 1)).fetchall()
    items = [control_record(row) for row in rows[:limit]]
    return {"items": items, "has_more": len(rows) > limit,
            "next_after_id": items[-1]["id"] if items else after_id}
