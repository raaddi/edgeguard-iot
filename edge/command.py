"""Send one explicit setpoint to a local MQTT node after observing fresh telemetry."""

import argparse
import json
import time
from uuid import uuid4

from contracts.commands import (CommandError, command_topic, decode_result,
                                result_topic, validate_command)
from contracts.telemetry import TelemetryError, decode_telemetry, telemetry_topic
from edge.mqtt import Connection, port_number


def send_command(connection, device, component, *, value=None, automatic=False, timeout=8):
    telemetry = None
    command = None
    result = None

    def received(client, userdata, packet):
        nonlocal telemetry, result
        if packet.retain:
            return
        try:
            if packet.topic == telemetry_topic(device):
                telemetry = decode_telemetry(packet.payload, topic=packet.topic)
            elif command is not None and packet.topic == result_topic(device):
                candidate = decode_result(packet.payload, topic=packet.topic)
                if (candidate["command_id"] == command["command_id"]
                        and candidate["component_id"] == component
                        and (candidate["boot_id"] == command["target_boot_id"]
                             or candidate["reason"] == "wrong_boot")):
                    result = candidate
        except (CommandError, TelemetryError):
            pass

    def wait_for(predicate, message):
        deadline = time.monotonic() + timeout
        while not predicate():
            connection.pump()
            if time.monotonic() >= deadline:
                raise TimeoutError(message)

    # Validate the device identifier before subscribing; no wildcard subscriptions.
    topic = command_topic(device)
    previous = connection.client.on_message
    connection.client.on_message = received
    try:
        connection.subscribe([telemetry_topic(device), result_topic(device)])
        wait_for(lambda: telemetry is not None, "No fresh telemetry; no command sent")
        command = {"schema_version": "1.0", "command_id": str(uuid4()), "device_id": device,
                   "target_boot_id": telemetry["boot_id"], "component_id": component,
                   "operation": "auto" if automatic else "set", "value": None if automatic else value,
                   "observed_uptime_ms": telemetry["uptime_ms"],
                   "expires_uptime_ms": telemetry["uptime_ms"] + 5000}
        validate_command(command)
        print(json.dumps({"command": command}), flush=True)
        connection.publish(topic, json.dumps(command).encode())
        wait_for(lambda: result is not None, "No node result; execution outcome is unknown")
        return result
    finally:
        connection.client.on_message = previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument("--component", required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--value", type=int)
    operation.add_argument("--auto", action="store_true")
    parser.add_argument("--port", type=port_number, default=1883)
    args = parser.parse_args()
    connection = Connection(args.port)
    try:
        connection.connect()
        result = send_command(connection, args.device, args.component, value=args.value, automatic=args.auto)
        print(json.dumps({"result": result}), flush=True)
        return 0 if result["status"] == "accepted" else 2
    except (OSError, ConnectionError, TimeoutError, CommandError, KeyboardInterrupt) as error:
        print(f"Command exchange stopped: {error}. No confirmed outcome; do not assume execution failed.")
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
