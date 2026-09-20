"""HTTP behaviour against real SQLite files, including a live collector writer."""

from copy import deepcopy
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from contracts.telemetry import telemetry_topic
from edge.api import create_app
from edge.readings import open_history
from edge.storage import TelemetryStore
from simulator.house import HouseSimulation


def ingest(store, message, received_at="2026-09-20T10:00:00+00:00"):
    return store.ingest(telemetry_topic(message["device_id"]), json.dumps(message).encode(),
                        received_at=received_at, received_monotonic_ns=123456)


@pytest.fixture
def history(tmp_path):
    path = tmp_path / "baza ze spacją #1.sqlite3"
    store = TelemetryStore(path)
    sim = HouseSimulation(node_count=3, extra_nodes=2)
    for _ in range(3):
        sim.step()
    for message in sim.history:
        ingest(store, message)
    with TestClient(create_app(path)) as client:
        yield client, store, sim, path
    store.close()


def test_devices_pagination_and_last_report(history):
    client, store, sim, path = history
    assert client.get('/health').json() == {"status": "ok", "database": "readable"}
    first = client.get('/devices?limit=2').json()
    second = client.get('/devices', params={"limit": 200, "after_device": first['next_after_device']}).json()
    items = first['items'] + second['items']
    assert first['has_more'] and not second['has_more']
    assert [item['device_id'] for item in items] == sorted(sim.nodes)
    assert all(item['message_count'] == 4 for item in items)
    node = items[0]['device_id']
    detail = client.get(f'/devices/{node}').json()
    assert detail['message_count'] == 4
    expected = next(m for m in reversed(sim.history) if m['device_id'] == node)
    assert detail['latest']['telemetry'] == expected
    assert detail['latest']['received_at'] != expected['timestamp']
    assert 'online' not in detail
    assert client.get('/openapi.json').status_code == 200
    assert client.get('/docs').status_code == 200


def test_cursor_survives_new_writes_duplicates_and_device_reboot(history):
    client, store, sim, path = history
    node = next(iter(sim.nodes))
    endpoint = f'/devices/{node}/telemetry'
    first = client.get(endpoint, params={"limit": 2}).json()
    assert first['has_more']
    message = deepcopy(next(m for m in sim.history if m['device_id'] == node))
    assert ingest(store, message) == 'duplicate'
    message['boot_id'] = '00000000-0000-4000-8000-000000000001'
    # A new session resets sequence/time; arrival order must still include it last.
    assert ingest(store, message, received_at="2026-09-20T09:00:00+00:00") == 'stored'
    second = client.get(endpoint, params={"after_id": first['next_after_id']}).json()
    items = first['items'] + second['items']
    assert len(items) == len({item['id'] for item in items}) == 5
    assert [item['telemetry']['sequence_number'] for item in items] == [0, 1, 2, 3, 0]
    assert items[-1]['telemetry'] == message
    assert client.get(f'/devices/{node}').json()['latest'] == items[-1]
    empty = client.get(endpoint, params={"after_id": second['next_after_id']}).json()
    assert empty == {"items": [], "has_more": False, "next_after_id": second['next_after_id']}


def test_unavailable_feedback_and_missing_messages_remain_missing(history):
    client, store, sim, path = history
    message = deepcopy(next(m for m in sim.history if m['actuators']))
    message['sequence_number'] = 100
    actuator = next(iter(message['actuators']))
    message['actuators'][actuator].update(reported=None, feedback='unavailable')
    ingest(store, message)
    result = client.get(f"/devices/{message['device_id']}/telemetry").json()['items']
    assert [item['telemetry']['sequence_number'] for item in result] == [0, 1, 2, 3, 100]
    assert result[-1]['telemetry']['actuators'][actuator]['reported'] is None


def test_empty_history_unknown_devices_and_no_writes(tmp_path):
    path = tmp_path / 'empty.sqlite3'
    store = TelemetryStore(path)
    store.close()
    before = path.read_bytes()
    with TestClient(create_app(path)) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/devices').json()['items'] == []
        assert client.get('/devices/absent').status_code == 404
        assert client.get('/devices/absent/telemetry').status_code == 404
        assert client.post('/devices').status_code == 405
    with open_history(path) as db:
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            db.execute('DELETE FROM telemetry')
    assert path.read_bytes() == before


@pytest.mark.parametrize('query', ['limit=0', 'limit=201', 'limit=oops', 'after_id=-1',
                                 'after_id=9223372036854775808'])
def test_invalid_telemetry_queries(history, query):
    client, store, sim, path = history
    node = next(iter(sim.nodes))
    assert client.get(f'/devices/{node}/telemetry?{query}').status_code == 422


def test_reject_invalid_ids_and_device_pagination(history):
    client, store, sim, path = history
    for url in ['/devices/bad.id', '/devices/' + 'x' * 65, '/devices?after_device=a%27', '/devices?limit=201']:
        assert client.get(url).status_code == 422
    assert client.get('/devices').status_code == 200


@pytest.mark.parametrize('kind', ['missing', 'wrong_schema', 'broken_file', 'invalid_payload'])
def test_unavailable_database_returns_503_without_creating_or_exposing_path(tmp_path, kind):
    path = tmp_path / 'private-name.sqlite3'
    if kind == 'wrong_schema':
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE unrelated (id INTEGER)')
        db.close()
    elif kind == 'broken_file':
        path.write_text('not a sqlite database')
    elif kind == 'invalid_payload':
        store = TelemetryStore(path)
        message = HouseSimulation(node_count=1).history[0]
        ingest(store, message)
        store.db.execute("UPDATE telemetry SET payload='{}'")
        store.db.commit()
        store.close()
    with TestClient(create_app(path)) as client:
        if kind == 'invalid_payload':
            response = client.get(f"/devices/{message['device_id']}/telemetry")
        else:
            response = client.get('/health')
            assert client.get('/devices').status_code == 503
        assert response.status_code == 503
        assert 'private-name' not in response.text
    if kind == 'missing':
        assert not path.exists()
