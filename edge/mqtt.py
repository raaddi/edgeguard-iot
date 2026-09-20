"""Small synchronous MQTT 3.1.1 adapter for the local laboratory."""

import time
from uuid import uuid4

import paho.mqtt.client as mqtt


class Connection:
    def __init__(self, port=1883, *, manual_ack=False):
        # This first transport increment deliberately supports loopback only.
        self.port = port
        self.connected = False
        self.error = None
        self.acknowledged = 0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"edgeguard-{uuid4().hex}",
                                  clean_session=True, manual_ack=manual_ack)
        self.client.connect_timeout = 2
        self.client.max_queued_messages_set(16)
        self.client.max_inflight_messages_set(10)
        self.client.on_connect = self._connected
        self.client.on_disconnect = self._disconnected
        self.on_connect = lambda: None

    def _connected(self, client, userdata, flags, reason, properties):
        self.connected = not reason.is_failure
        self.error = str(reason) if reason.is_failure else None
        if self.connected:
            self.on_connect()

    def _disconnected(self, client, userdata, flags, reason, properties):
        self.connected = False

    def connect(self, timeout=3):
        self.connected = False
        self.error = None
        self.client.connect("127.0.0.1", self.port, keepalive=30)
        deadline = time.monotonic() + timeout
        while not self.connected:
            self.pump()
            if self.error or time.monotonic() >= deadline:
                raise ConnectionError(self.error or "MQTT connection timed out")

    def pump(self):
        result = self.client.loop(timeout=0.1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(mqtt.error_string(result))

    def publish(self, topic, payload, timeout=3):
        info = self.client.publish(topic, payload, qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(mqtt.error_string(info.rc))
        deadline = time.monotonic() + timeout
        while not info.is_published():
            self.pump()
            if time.monotonic() >= deadline:
                raise TimeoutError("Broker acknowledgement timed out; delivery is uncertain")
        self.acknowledged += 1

    def subscribe(self, topics, timeout=3):
        """Wait for SUBACK before callers advertise readiness (outside callbacks)."""
        replies = {}
        previous = self.client.on_subscribe
        self.client.on_subscribe = lambda client, userdata, mid, reasons, properties: replies.update(
            {mid: reasons})
        try:
            result, mid = self.client.subscribe([(topic, 1) for topic in topics])
            if result != mqtt.MQTT_ERR_SUCCESS:
                raise ConnectionError(mqtt.error_string(result))
            deadline = time.monotonic() + timeout
            while mid not in replies:
                self.pump()
                if time.monotonic() >= deadline:
                    raise TimeoutError("MQTT subscription timed out")
            if len(replies[mid]) != len(topics) or any(r.is_failure for r in replies[mid]):
                raise ConnectionError("MQTT subscription rejected")
        finally:
            self.client.on_subscribe = previous

    def close(self):
        self.client.disconnect()
        self.client.loop(timeout=0.1)


def port_number(value):
    import argparse
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535")
    return port
