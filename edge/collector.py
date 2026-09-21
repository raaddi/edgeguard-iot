"""Persist local MQTT telemetry and command observations before acknowledging."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import sqlite3
import time

from contracts.telemetry import TelemetryError
from contracts.commands import CommandError
from edge.mqtt import Connection, port_number
from edge.storage import TelemetryStore

TOPICS = ["edgeguard/devices/+/telemetry", "edgeguard/devices/+/commands",
          "edgeguard/devices/+/command-results"]


class Collector:
    def __init__(self, database, port=1883):
        self.store = TelemetryStore(database)
        self.connection = Connection(port, manual_ack=True)
        self.connection.on_connect = self._subscribe
        self.connection.client.on_subscribe = self._subscribed
        self.connection.client.on_message = self._message
        self.ready = False
        self.subscription_error = False
        self.subscription_mid = None
        self.counts = Counter(stored=0, duplicate=0, conflict=0, invalid=0, retained=0,
                              storage_errors=0, connections=0, disconnects=0, control_stored=0)

    def _subscribe(self):
        self.ready = False
        self.subscription_error = False
        self.counts["connections"] += 1
        result, self.subscription_mid = self.connection.client.subscribe([(topic, 1) for topic in TOPICS])
        if result != 0:
            raise ConnectionError("MQTT subscribe failed")

    def _subscribed(self, client, userdata, mid, reasons, properties):
        if mid != self.subscription_mid:
            return
        self.subscription_error = len(reasons) != len(TOPICS) or any(reason.is_failure for reason in reasons)
        self.ready = not self.subscription_error

    def _message(self, client, userdata, message):
        # Single network/SQLite thread: no unbounded application message queue.
        received_at = datetime.now(timezone.utc).isoformat()
        received_ns = time.monotonic_ns()
        if message.retain:
            self.counts["retained"] += 1
        else:
            try:
                if message.topic.endswith("/telemetry"):
                    outcome = self.store.ingest(message.topic, message.payload,
                                                received_at=received_at,
                                                received_monotonic_ns=received_ns)
                    self.counts[outcome] += 1
                else:
                    self.store.ingest_control(message.topic, message.payload,
                                              received_at=received_at, received_monotonic_ns=received_ns,
                                              mqtt_qos=message.qos, mqtt_duplicate=message.dup)
                    self.counts["control_stored"] += 1
            except (TelemetryError, CommandError):
                self.counts["invalid"] += 1
            except sqlite3.Error:
                self.counts["storage_errors"] += 1
                raise  # No acknowledgement: terminate on a failed write.
        # Invalid/conflicting/retained records are intentionally rejected and counted.
        if message.qos:
            result = client.ack(message.mid, message.qos)
            if result != 0:
                raise ConnectionError("MQTT acknowledgement failed")

    def connect(self):
        self.connection.connect()
        deadline = time.monotonic() + 3
        while not self.ready:
            self.connection.pump()
            if self.subscription_error or time.monotonic() >= deadline:
                raise ConnectionError("MQTT subscription rejected or timed out")

    def run(self, duration=0, *, on_ready=lambda: None, stop=None):
        self.connect()
        on_ready()
        deadline = time.monotonic() + duration if duration else float("inf")
        while time.monotonic() < deadline and not (stop and stop.is_set()):
            try:
                self.connection.pump()
            except (ConnectionError, OSError):
                self.ready = False
                self.counts["disconnects"] += 1
                while time.monotonic() < deadline and not (stop and stop.is_set()):
                    time.sleep(0.2)
                    try:
                        self.connect()
                        on_ready()
                        break
                    except (ConnectionError, OSError):
                        continue

    def close(self):
        try:
            self.connection.close()
        finally:
            self.store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/telemetry.sqlite3")
    parser.add_argument("--port", type=port_number, default=1883)
    parser.add_argument("--seconds", type=int, default=0, help="0 = run until Ctrl+C")
    args = parser.parse_args()
    if args.seconds < 0:
        parser.error("Seconds cannot be negative")
    collector = None
    try:
        collector = Collector(args.database, args.port)
        collector.run(args.seconds, on_ready=lambda: print("READY: MQTT subscription active", flush=True))
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError, ConnectionError, sqlite3.Error) as error:
        print(f"Collector failed: {error}", flush=True)
        return 1
    finally:
        if collector:
            print(json.dumps(dict(collector.counts)), flush=True)
            collector.close()


if __name__ == "__main__":
    raise SystemExit(main())
