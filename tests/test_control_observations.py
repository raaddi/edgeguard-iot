"""Durable receipts preserve repeats without claiming execution or causality."""

import json
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from contracts.commands import CommandError, command_topic, result_topic
from edge.api import create_app
from edge.collector import Collector, TOPICS
from edge.observations import control_history
from edge.readings import open_history
from edge.storage import TelemetryStore


@pytest.fixture
def messages():
    command_id, boot = str(uuid4()), str(uuid4())
    command = {"schema_version": "1.0", "command_id": command_id, "device_id": "esp32_node_01",
               "target_boot_id": boot, "component_id": "led_01", "operation": "set", "value": 1,
               "observed_uptime_ms": 1000, "expires_uptime_ms": 6000}
    result = {"schema_version": "1.0", "command_id": command_id, "device_id": "esp32_node_01",
              "boot_id": boot, "component_id": "led_01", "status": "accepted", "reason": None,
              "handled_uptime_ms": 1000}
    return command, result


def save(store, message, *, duplicate=False, at="2026-09-21T10:00:00+00:00", ns=100):
    topic = command_topic(message["device_id"]) if "operation" in message else result_topic(message["device_id"])
    return store.ingest_control(topic, json.dumps(message).encode(), mqtt_qos=1,
                                mqtt_duplicate=duplicate, received_at=at, received_monotonic_ns=ns)


def test_repeats_conflicts_orphan_results_and_restarts_are_separate_receipts(tmp_path, messages):
    path = tmp_path / "history.sqlite3"
    command, result = messages
    store = TelemetryStore(path)
    session = store.collector_session_id
    try:
        ids = [save(store, result), save(store, command), save(store, command, duplicate=True),
               save(store, {**command, "value": 0}), save(store, result)]
        assert ids == [1, 2, 3, 4, 5]
    finally:
        store.close()
    store = TelemetryStore(path)
    try:
        assert store.collector_session_id != session
        assert save(store, command, at="2026-09-21T09:00:00+00:00", ns=1) == 6
        with open_history(path) as db:
            page = control_history(db, command["device_id"], after_id=0, limit=200)
        items = page["items"]
        assert [r["kind"] for r in items] == ["result", "command", "command", "command", "result", "command"]
        assert [r["message"] for r in items] == [result, command, command, {**command, "value": 0}, result, command]
        assert items[2]["mqtt_duplicate"] and not items[1]["mqtt_duplicate"]
        assert items[0]["collector_session_id"] == session
        assert items[-1]["collector_session_id"] != session
        assert items[-1]["received_at"] < items[0]["received_at"]  # Wall clock is not the cursor.
        assert items[0]["message"]["handled_uptime_ms"] != items[0]["received_monotonic_ns"]
    finally:
        store.close()


@pytest.mark.parametrize("payload,topic", [
    (b"{}", command_topic("esp32_node_01")),
    (b"x" * 4097, command_topic("esp32_node_01")),
    (b'{"command_id":"x","command_id":"y"}', result_topic("esp32_node_01")),
])
def test_invalid_payload_is_never_stored(tmp_path, payload, topic):
    store = TelemetryStore(tmp_path / "invalid.sqlite3")
    try:
        with pytest.raises(CommandError):
            store.ingest_control(topic, payload, mqtt_qos=1, mqtt_duplicate=False)
        assert store.db.execute("SELECT count(*) FROM control_observations").fetchone()[0] == 0
    finally:
        store.close()


def test_topic_mismatch_rejected_and_boot_rejection_preserved(tmp_path, messages):
    command, result = messages
    store = TelemetryStore(tmp_path / "boots.sqlite3")
    try:
        with pytest.raises(CommandError):
            store.ingest_control(command_topic("wrong"), json.dumps(command).encode(),
                                 mqtt_qos=1, mqtt_duplicate=False)
        result.update(boot_id=str(uuid4()), status="rejected", reason="wrong_boot")
        save(store, command)
        save(store, result)
        boots = store.db.execute("SELECT message_boot_id FROM control_observations ORDER BY id").fetchall()
        assert [row[0] for row in boots] == [command["target_boot_id"], result["boot_id"]]
    finally:
        store.close()


def test_collector_commits_control_before_ack_and_failure_has_no_ack(tmp_path, messages):
    collector = Collector(tmp_path / "ack.sqlite3")
    command, result = messages
    observed_counts = []
    def ack(mid, qos):
        with sqlite3.connect(tmp_path / "ack.sqlite3") as reader:
            observed_counts.append(reader.execute("SELECT count(*) FROM control_observations").fetchone()[0])
        return 0
    client = SimpleNamespace(ack=ack)
    packet = SimpleNamespace(topic=command_topic(command["device_id"]), payload=json.dumps(command).encode(),
                             retain=False, qos=1, dup=False, mid=10)
    try:
        collector._message(client, None, packet)
        assert observed_counts == [1]
        assert collector.counts["control_stored"] == 1 and collector.counts["stored"] == 0
        collector.store.db.execute("""CREATE TRIGGER fail_control BEFORE INSERT ON control_observations
            BEGIN SELECT RAISE(FAIL, 'disk failure'); END""")
        collector.store.db.commit()
        with pytest.raises(sqlite3.Error):
            collector._message(client, None, packet)
        assert observed_counts == [1]
        assert collector.counts["storage_errors"] == 1
        assert collector.counts["control_stored"] == 1
    finally:
        collector.close()


def test_collector_rejects_retained_and_invalid_but_acks_them(tmp_path, messages):
    collector = Collector(tmp_path / "rejected.sqlite3")
    command, _ = messages
    acknowledgements = []
    client = SimpleNamespace(ack=lambda mid, qos: acknowledgements.append((mid, qos)) or 0)
    packet = SimpleNamespace(topic=command_topic(command["device_id"]), payload=json.dumps(command).encode(),
                             retain=True, qos=1, dup=False, mid=10)
    try:
        collector._message(client, None, packet)
        packet.retain, packet.payload = False, b"not-json"
        collector._message(client, None, packet)
        assert len(acknowledgements) == 2
        assert collector.counts["retained"] == 1 and collector.counts["invalid"] == 1
        assert collector.store.db.execute("SELECT count(*) FROM control_observations").fetchone()[0] == 0
    finally:
        collector.close()


def test_subscriptions_require_all_topics_and_current_packet_id(tmp_path):
    collector = Collector(tmp_path / "subscription.sqlite3")
    success = SimpleNamespace(is_failure=False)
    failure = SimpleNamespace(is_failure=True)
    try:
        collector.subscription_mid = 7
        collector._subscribed(None, None, 6, [success] * len(TOPICS), None)
        assert not collector.ready
        collector._subscribed(None, None, 7, [success], None)
        assert not collector.ready and collector.subscription_error
        collector._subscribed(None, None, 7, [success, success, failure], None)
        assert not collector.ready
        collector._subscribed(None, None, 7, [success] * len(TOPICS), None)
        assert collector.ready
    finally:
        collector.close()


def test_api_paginates_filters_and_does_not_require_telemetry(tmp_path, messages):
    path = tmp_path / "api.sqlite3"
    command, result = messages
    store = TelemetryStore(path)
    try:
        save(store, command)
        save(store, result)
        save(store, command)
        save(store, {**command, "command_id": str(uuid4())})
        with TestClient(create_app(path)) as api:
            endpoint = f"/devices/{command['device_id']}/control-history"
            assert api.get("/devices").json()["items"] == []
            first = api.get(endpoint, params={"limit": 2, "command_id": command["command_id"]}).json()
            second = api.get(endpoint, params={"limit": 2, "after_id": first["next_after_id"],
                                              "command_id": command["command_id"]}).json()
            assert first["has_more"] and not second["has_more"]
            assert [r["id"] for r in first["items"] + second["items"]] == [1, 2, 3]
            assert first["items"][0]["message"] == command
            assert first["items"][1]["message"] == result
            empty = api.get(endpoint, params={"after_id": 4}).json()
            assert empty == {"items": [], "has_more": False, "next_after_id": 4}
            assert api.get("/devices/unknown/control-history").json()["items"] == []
            assert api.post(endpoint, json=command).status_code == 405
            for query in ["limit=201", "limit=0", "after_id=-1", "command_id=bad", "after_id=9223372036854775808"]:
                assert api.get(endpoint + "?" + query).status_code == 422
    finally:
        store.close()


@pytest.mark.parametrize("corruption", ["payload", "device_id", "command_id", "kind", "message_boot_id", "component_id"])
def test_api_rejects_corrupt_observations(tmp_path, messages, corruption):
    path = tmp_path / "private.sqlite3"
    store = TelemetryStore(path)
    try:
        save(store, messages[0])
        value = "result" if corruption == "kind" else "bad"
        # Column names are the fixed test parametrization, never request input.
        store.db.execute(f"UPDATE control_observations SET {corruption}=?", (value,))
        store.db.commit()
        with TestClient(create_app(path)) as api:
            node = "bad" if corruption == "device_id" else messages[0]["device_id"]
            response = api.get(f"/devices/{node}/control-history")
            assert response.status_code == 503
            assert "private.sqlite3" not in response.text
    finally:
        store.close()


def test_additive_schema_preserves_old_telemetry_and_api_never_migrates(tmp_path, messages):
    path = tmp_path / "older.sqlite3"
    store = TelemetryStore(path)
    from simulator.house import HouseSimulation
    from contracts.telemetry import telemetry_topic
    telemetry = HouseSimulation(node_count=1).history[0]
    store.ingest(telemetry_topic(telemetry["device_id"]), json.dumps(telemetry).encode())
    store.db.execute("DROP TABLE control_observations")
    store.db.commit()
    store.close()
    before = path.read_bytes()
    with TestClient(create_app(path)) as api:
        assert api.get("/health").status_code == 200
        assert api.get("/devices/esp32_node_01/control-history").status_code == 503
    assert path.read_bytes() == before
    store = TelemetryStore(path)
    try:
        assert store.db.execute("SELECT count(*) FROM telemetry").fetchone()[0] == 1
        assert save(store, messages[0]) > 0
        with TestClient(create_app(path)) as api:
            assert api.get("/devices/esp32_node_01/control-history").status_code == 200
    finally:
        store.close()
