"""Shared real-broker fixture for MQTT integration tests."""

import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import pytest


def wait_until(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.03)
    raise AssertionError("Timed out waiting for MQTT condition")


@pytest.fixture
def broker(tmp_path):
    binary = os.environ.get("MOSQUITTO_EXECUTABLE") or shutil.which("mosquitto")
    if not binary:
        local = Path(__file__).resolve().parents[1] / ".tools/mosquitto/mosquitto.exe"
        binary = str(local) if local.exists() else None
    if not binary:
        if os.environ.get("REQUIRE_MQTT_TESTS") == "1":
            pytest.fail("Mosquitto is required for integration tests")
        pytest.skip("Install Mosquitto or set MOSQUITTO_EXECUTABLE for integration tests")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    root = Path(__file__).resolve().parents[1]
    config = tmp_path / "mosquitto.conf"
    config.write_text((root / "mqtt/mosquitto-local.conf").read_text().replace(
        "listener 1883", f"listener {port}"), encoding="utf-8")

    class Broker:
        process = None

        def start(self):
            self.process = subprocess.Popen([binary, "-c", str(config)],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            def listening():
                assert self.process.poll() is None, "Mosquitto did not start"
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        return True
                except OSError:
                    return False
            wait_until(listening)

        def stop(self):
            if self.process and self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=5)

    instance = Broker()
    instance.port = port
    try:
        instance.start()
        yield instance
    finally:
        instance.stop()
