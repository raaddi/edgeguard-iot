"""Bounded command handling for the shared house model; no hardware assumptions."""

from collections import Counter, deque
from copy import deepcopy
import json
import time

from contracts.commands import (CommandError, command_topic, decode_command,
                                result_topic, target_rejection, validate_command,
                                validate_result)
from contracts.telemetry import telemetry_topic
from simulator.telemetry import session_id


class CommandProcessor:
    CACHE_PER_NODE = 256

    def __init__(self, simulation):
        self.sim = simulation
        self.cache = {node: {} for node in simulation.nodes}
        self.counts = Counter()
        self.capabilities = {
            node: {cid: {"kind": item["kind"],
                         "allowed_values": [0, 110] if item["kind"] == "servo" else [0, 1]}
                   for cid, item in simulation.components.items() if item["node"] == node}
            for node in simulation.nodes}

    def handle(self, command):
        validate_command(command)
        node = command["device_id"]
        if node not in self.sim.nodes or not self.sim.nodes[node]:
            self.counts["unavailable"] += 1
            return None
        boot = session_id(self.sim.run_id, node)
        uptime = (self.sim.time - 1) * 1000
        cache = self.cache[node]
        fingerprint = json.dumps(command, sort_keys=True, separators=(",", ":"))
        cached = cache.get(command["command_id"])
        # Old-boot requests never retrieve/overwrite this session's results.
        if command["target_boot_id"] != boot:
            reason = "wrong_boot"
        elif cached is not None:
            if cached[0] == fingerprint:
                self.counts["duplicate"] += 1
                return deepcopy(cached[1])
            reason = "duplicate_conflict"
        elif len(cache) >= self.CACHE_PER_NODE:
            reason = "capacity_exceeded"
        else:
            reason = target_rejection(command, device_id=node, boot_id=boot,
                                      uptime_ms=uptime, capabilities=self.capabilities[node])
            if reason is None:
                if len(self.sim.actions) >= self.sim.MAX_ACTIONS:
                    reason = "capacity_exceeded"
                else:
                    try:
                        if command["operation"] == "auto":
                            applied = self.sim.auto_fan(command["component_id"])
                        else:
                            applied = self.sim.command(command["component_id"], command["value"])
                        if not applied:
                            reason = "internal_error"
                    except (ValueError, KeyError):
                        reason = "internal_error"
        result = {"schema_version": "1.0", "command_id": command["command_id"],
                  "device_id": node, "boot_id": boot, "component_id": command["component_id"],
                  "status": "rejected" if reason else "accepted", "reason": reason,
                  "handled_uptime_ms": uptime}
        validate_result(result)
        if command["target_boot_id"] == boot and cached is None and len(cache) < self.CACHE_PER_NODE:
            # No eviction: a duplicate cannot become executable again during this run.
            cache[command["command_id"]] = (fingerprint, deepcopy(result))
        self.counts[result["status"]] += 1
        return result


class CommandReceiver:
    QUEUE_LIMIT = 64
    EVENT_LIMIT = 1000

    def __init__(self, simulation, connection):
        self.sim, self.connection = simulation, connection
        self.processor = CommandProcessor(simulation)
        self.pending = deque()
        self.events = deque(maxlen=self.EVENT_LIMIT)
        self.counts = Counter()
        self.topics = {command_topic(node) for node in simulation.nodes}
        connection.client.on_message = self._message

    def _message(self, client, userdata, packet):
        # Never publish synchronously here: publish() pumps this same network loop.
        if packet.retain:
            self.counts["retained"] += 1
            return
        if packet.topic not in self.topics:
            self.counts["invalid"] += 1
            return
        try:
            command = decode_command(packet.payload, topic=packet.topic)
        except CommandError:
            self.counts["invalid"] += 1
            return
        if not self.sim.nodes[command["device_id"]]:
            self.counts["offline"] += 1
        elif len(self.pending) >= self.QUEUE_LIMIT:
            self.counts["queue_full"] += 1
        else:
            self.pending.append(command)

    def connect(self):
        self.connection.connect()
        self.connection.subscribe(sorted(self.topics))

    def service(self):
        self.connection.pump()
        # A flood cannot keep this loop draining forever and starve telemetry.
        for _ in range(min(len(self.pending), 16)):
            command = self.pending.popleft()
            result = self.processor.handle(command)
            if result is None:
                continue
            if len(self.events) == self.events.maxlen:
                self.counts["evicted_events"] += 1
            self.events.append({"command": command, "result": result})
            # The outcome is cached BEFORE publishing; a retry never repeats the action.
            self.connection.publish(result_topic(result["device_id"]), json.dumps(result).encode())
            self.counts["results_broker_acked"] += 1

    def publish_telemetry(self):
        for message in list(self.sim.history)[-len(self.sim.nodes):]:
            if message["sequence_number"] == self.sim.time - 1:
                self.connection.publish(telemetry_topic(message["device_id"]), json.dumps(message).encode())
                self.counts["telemetry_broker_acked"] += 1

    def run(self, steps, interval=1):
        if not 1 <= steps <= self.sim.MAX_STEPS - self.sim.time + 1 or interval <= 0:
            raise ValueError("Invalid command receiver run length or interval")
        self.publish_telemetry()
        for _ in range(steps - 1):
            deadline = time.monotonic() + interval
            while time.monotonic() < deadline:
                self.service()
            self.sim.step()
            self.publish_telemetry()

    def export(self):
        return {"receiver_counts": dict(self.counts), "processor_counts": dict(self.processor.counts),
                "pending_at_stop": len(self.pending), "events": list(self.events)}
