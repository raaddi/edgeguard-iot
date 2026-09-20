"""Qt reads real HTTP/SQLite; slow/broken responses cannot replace the wrong view."""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import socket
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import uvicorn

from contracts.telemetry import telemetry_topic
from edge.api import create_app
from edge.storage import TelemetryStore
from simulator.house import HouseSimulation
from simulator.desktop.api_client import ApiClient
from simulator.desktop.collector_view import CollectorView, channel_samples
from simulator.desktop.window import LaboratoryWindow


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def until(condition, timeout=5):
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, 'Timed out waiting for Qt/HTTP'
        QApplication.processEvents()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.01)


@pytest.fixture
def live_api(tmp_path):
    path = tmp_path / 'history.sqlite3'
    store = TelemetryStore(path)
    sim = HouseSimulation(node_count=1)
    initial = deepcopy(sim.history[0])
    initial['device_id'] = 'independent_node'

    def insert(message):
        store.ingest(telemetry_topic(message['device_id']), json.dumps(message).encode())

    insert(initial)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(path), log_level='error', lifespan='off'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started:
        assert thread.is_alive() and time.monotonic() < deadline
        time.sleep(0.01)
    try:
        yield port, initial, insert
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()
        store.close()
        assert not thread.is_alive()


def test_qt_loads_http_history_refreshes_and_separates_boots(app, live_api):
    port, initial, insert = live_api
    view = CollectorView()
    view.port.setValue(port)
    view.show()
    try:
        view.connect_button.click()
        until(lambda: len(view.records) == 1)
        assert view.nodes.currentData() == 'independent_node'
        assert len(view.plots) == 24
        assert 'simulated' in view.raw.toPlainText()
        missing = deepcopy(initial)
        missing['sequence_number'] = 3
        missing['actuators']['servo_01'].update(reported=None, feedback='unavailable')
        insert(missing)
        view.refresh_button.click()
        until(lambda: len(view.records) == 2)
        assert channel_samples(view.records, 'servo_01') == [(0, 0), (3, None), (3, None)]
        assert channel_samples(view.records, 'servo_01', 'commanded')[-1] == (3, 0)
        reboot = deepcopy(initial)
        reboot['boot_id'] = '00000000-0000-4000-8000-000000000002'
        insert(reboot)
        view.refresh_button.click()
        until(lambda: len(view.records) == 3)
        assert view.boots.count() == 2
        assert view.boots.currentData() == initial['boot_id']
        view.boots.setCurrentIndex(view.boots.findData(reboot['boot_id']))
        assert len(view.plots['servo_01'].records) == 1
        assert not view.grab().isNull()
        view.port.setValue(port + 1 if port < 65535 else port - 1)
        assert not view.records and not view.plots and view.nodes.count() == 0
    finally:
        view.stop()
        view.close()
        view.deleteLater()


def test_switching_source_pauses_local_model_and_preserves_unsaved_work(app):
    window = LaboratoryWindow()
    window.show()
    window.single_step.click()
    model, history = window.sim, list(window.sim.history)
    window.play.click()
    window.source.setCurrentIndex(1)
    assert not window.timer.isActive()
    assert window.dirty and not window.experiment_menu.isEnabled()
    assert all(not action.isEnabled() for action in window.experiment_menu.actions())
    window.collector_view.auto.setChecked(True)
    window.source.setCurrentIndex(0)
    assert not window.collector_view.timer.isActive()
    assert window.sim is model and list(window.sim.history) == history
    assert window.experiment_menu.isEnabled()
    window.dirty = False
    window.close()
    window.deleteLater()


@pytest.fixture
def fault_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == '/slow':
                time.sleep(0.3)
            self.send_response(302 if self.path == '/redirect' else 503 if self.path == '/unavailable' else 200)
            if self.path == '/redirect':
                self.send_header('Location', '/ok')
            self.end_headers()
            try:
                self.wfile.write(b'x' * 2048 if self.path == '/big' else b'not-json' if self.path == '/bad' else b'{"items": []}')
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port
    server.shutdown()
    server.server_close()
    thread.join(3)


@pytest.mark.parametrize('path,expected', [('/bad', 'JSON'), ('/big', '8 MiB'),
                                         ('/unavailable', 'HTTP 503'), ('/redirect', 'HTTP 302'),
                                         ('/slow', 'wyznaczonym czasie')])
def test_network_errors_are_bounded_and_reported(app, fault_server, path, expected):
    client = ApiClient(app, timeout_ms=100 if path == '/slow' else 2000)
    client.MAX_BYTES = 1024
    results = []
    client.result.connect(lambda *result: results.append(result))
    client.get(fault_server, path, 'request')
    until(lambda: bool(results))
    assert expected in results[0][2]
    assert client.reply is None


def test_cancelled_request_cannot_overwrite_new_response(app, fault_server):
    client = ApiClient(app)
    results = []
    client.result.connect(lambda *result: results.append(result))
    client.get(fault_server, '/slow', 'old')
    QTest.qWait(20)
    client.get(fault_server, '/ok', 'new')
    until(lambda: bool(results))
    QTest.qWait(350)
    assert len(results) == 1 and results[0][0] == 'new' and not results[0][2]


def test_invalid_response_and_api_failure_preserve_last_good_data(app, live_api):
    port, initial, insert = live_api
    view = CollectorView()
    view.port.setValue(port)
    view.load_devices()
    until(lambda: len(view.records) == 1)
    previous = view.records
    view.received('independent_node', {'items': [{}], 'older_available': False}, '')
    assert view.records is previous and 'Niepoprawna' in view.status.text()
    view.received('independent_node', None, 'HTTP 503')
    assert view.records is previous and 'nie zostały odświeżone' in view.status.text()
    view.stop()
    view.close()
    view.deleteLater()
