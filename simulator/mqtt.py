"""Publish a bounded headless house run through the local MQTT broker."""

import argparse
import json
from pathlib import Path
import time
from uuid import uuid4

from contracts.telemetry import telemetry_topic, validate_telemetry
from edge.mqtt import Connection, port_number
from simulator.__main__ import code_version, identifier
from simulator.house import HouseSimulation


def publish_run(sim, connection, steps, interval=1):
    acknowledged = 0
    for index in range(steps):
        if index:
            time.sleep(interval)
            sim.step()
        tick = sim.time - 1
        for message in list(sim.history)[-len(sim.nodes):]:
            if message["sequence_number"] != tick:
                continue
            validate_telemetry(message)
            connection.publish(telemetry_topic(message["device_id"]),
                               json.dumps(message, allow_nan=False).encode())
            acknowledged += 1
    return acknowledged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=int, choices=range(1, 33), default=3)
    parser.add_argument("--extra-nodes", type=int, choices=range(33), default=0)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run-id", type=identifier, default=f"mqtt-{uuid4().hex}")
    parser.add_argument("--port", type=port_number, default=1883)
    args = parser.parse_args()
    if not 1 <= args.steps <= HouseSimulation.MAX_STEPS or not 0 <= args.seed <= 2**31 - 1:
        parser.error("Steps must be 1..10000 and seed 0..2147483647")
    sim = HouseSimulation(args.seed, args.nodes, args.extra_nodes, args.run_id)
    archive = Path("experiments/runs") / f"{args.run_id}-mqtt.json"
    archive.parent.mkdir(parents=True, exist_ok=True)
    # Never overwrite an earlier run or accidentally reuse its deterministic boot IDs.
    try:
        output = archive.open("x", encoding="utf-8")
    except FileExistsError:
        parser.error("Run archive already exists; choose another --run-id")
    connection = Connection(args.port)
    version = code_version()
    result = {"status": "failed", "broker_acked": None, "collector_delivery": "unverified"}
    try:
        connection.connect()
        result["broker_acked"] = publish_run(sim, connection, args.steps)
        result["status"] = "completed"
        print(json.dumps(result))
        return 0
    except (OSError, ConnectionError, TimeoutError, KeyboardInterrupt) as error:
        print(f"Publisher stopped: {error}; verify delivery in the collector database")
        return 1
    finally:
        connection.close()
        result["broker_acked"] = connection.acknowledged
        with output:
            json.dump({**sim.export(version), "transport": result}, output, indent=2)
        print(f"Archive: {archive}")


if __name__ == "__main__":
    raise SystemExit(main())
