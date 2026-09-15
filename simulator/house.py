"""Deterministic behavioural model; no network or interface dependencies."""

from collections import deque
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import platform
from pathlib import Path

from simulator.normal_activity import gas_signal
from simulator.telemetry import START, session_id

SCENARIOS = {"gas_spike": "Wzrost sygnału gazu", "sensor_freeze": "Zamrożenie czujnika",
             "fan_failure": "Awaria wentylatora", "node_offline": "Utrata łączności węzła"}


def load_profile() -> dict:
    return json.loads((Path(__file__).parent / "config/house.json").read_text(encoding="utf-8"))


class HouseSimulation:
    VERSION = "house-behaviour-v1"
    MAX_STEPS = 10_000
    MAX_ACTIONS = 1_000
    HISTORY_LIMIT = 3_000

    def __init__(self, seed=42, node_count=3, extra_nodes=0, run_id="house-demo", profile=None):
        if not isinstance(seed, int) or not 1 <= node_count <= 32 or not 0 <= extra_nodes <= 32:
            raise ValueError("Invalid seed or node counts.")
        self.seed, self.node_count, self.extra_nodes, self.run_id = seed, node_count, extra_nodes, run_id
        self.profile = deepcopy(profile if profile is not None else load_profile())
        ids = [c["id"] for c in self.profile["components"]]
        room_ids = [r["id"] for r in self.profile["rooms"]]
        if len(ids) != len(set(ids)) or len(room_ids) != len(set(room_ids)):
            raise ValueError("Duplicate component or room identifiers.")
        if not 0 <= self.profile["threshold"] <= 1:
            raise ValueError("Invalid threshold.")
        self.nodes = {f"esp32_node_{i+1:02}": True for i in range(node_count)}
        self.room_nodes = {room: list(self.nodes)[i % node_count] for i, room in enumerate(room_ids)}
        self.components = {}
        for item in self.profile["components"]:
            if item["room"] not in room_ids or item["kind"] not in {"gas", "light", "fan", "servo"}:
                raise ValueError("Invalid component configuration.")
            self.components[item["id"]] = {**item, "node": self.room_nodes[item["room"]]}
        for item in self.components.values():
            if item["kind"] == "fan" and (
                item.get("sensor") not in self.components
                or self.components[item["sensor"]]["kind"] != "gas"
                or self.components[item["sensor"]]["node"] != item["node"]
            ):
                raise ValueError("Fan must reference a gas sensor on the same node.")
        for i in range(extra_nodes):
            node = f"virtual_node_{i+1:02}"
            self.nodes[node] = True
            sensor = f"virtual_gas_{i+1:02}"
            self.components[sensor] = {"id": sensor, "kind": "gas", "room": "virtual",
                                       "node": node, "name": f"Dodatkowy czujnik {i+1}"}
        self.sensors = {}
        self.actuators = {}
        for cid, item in self.components.items():
            if item["kind"] == "gas":
                derived_seed = int.from_bytes(sha256(f"{seed}:{cid}".encode()).digest()[:8], "big")
                self.sensors[cid] = {"generator": gas_signal(derived_seed), "value": 0.2,
                                     "environment": 0.2, "excess": 0.0}
            else:
                self.actuators[cid] = {"commanded": 0, "simulated": 0, "mode": "auto" if item["kind"] == "fan" else "manual"}
        self.time = 0
        self.actions = []
        self.scenarios = []
        self.alerts = []
        self.history = deque(maxlen=self.HISTORY_LIMIT)
        self.evicted_messages = 0
        self.suppressed_messages = 0
        self.message_count = 0
        self.step()

    def _record(self, action):
        if len(self.actions) >= self.MAX_ACTIONS:
            raise ValueError("Action limit reached; export and start a new run.")
        self.actions.append({"at_step": self.time, **action})

    def command(self, component_id, value):
        item = self.components[component_id]
        if component_id not in self.actuators:
            raise ValueError("Not an actuator.")
        allowed = {0, 110} if item["kind"] == "servo" else {0, 1}
        if value not in allowed:
            raise ValueError("Invalid actuator value.")
        accepted = self.nodes[item["node"]]
        self._record({"type": "command", "target": component_id, "value": value, "accepted": accepted})
        if not accepted:
            return False
        state = self.actuators[component_id]
        state["commanded"] = value
        state["mode"] = "manual"
        state["simulated"] = 0 if self._active("fan_failure", component_id, self.time - 1) else value
        return True

    def auto_fan(self, component_id):
        if self.components[component_id]["kind"] != "fan":
            raise ValueError("Not a fan.")
        accepted = self.nodes[self.components[component_id]["node"]]
        self._record({"type": "auto", "target": component_id, "accepted": accepted})
        if accepted:
            self.actuators[component_id]["mode"] = "auto"
        return accepted

    def inject(self, kind, target, duration=20):
        expected = {"gas_spike": self.sensors, "sensor_freeze": self.sensors,
                    "fan_failure": {c for c, d in self.components.items() if d["kind"] == "fan"},
                    "node_offline": self.nodes}
        if kind not in expected or target not in expected[kind] or not 1 <= duration <= 600:
            raise ValueError("Invalid scenario or duration.")
        scenario = {"kind": kind, "target": target, "start": self.time, "end": self.time + duration}
        if kind == "sensor_freeze":
            scenario["frozen_value"] = self.sensors[target]["value"]
        self._record({"type": "scenario", **scenario})
        self.scenarios.append(scenario)

    def _active(self, kind, target, tick):
        return next((s for s in reversed(self.scenarios) if s["kind"] == kind and s["target"] == target
                     and s["start"] <= tick < s["end"]), None)

    def step(self):
        if self.time >= self.MAX_STEPS:
            raise ValueError("Run limit reached; export and reset the simulation.")
        tick = self.time
        for node in self.nodes:
            self.nodes[node] = not bool(self._active("node_offline", node, tick))
        for cid, sensor in self.sensors.items():
            base = next(sensor["generator"])
            sensor["excess"] = 0.6 if self._active("gas_spike", cid, tick) else sensor["excess"] * 0.85
            sensor["environment"] = min(1.0, round(base + sensor["excess"], 6))
            frozen = self._active("sensor_freeze", cid, tick)
            sensor["value"] = frozen["frozen_value"] if frozen else sensor["environment"]
        for cid, state in self.actuators.items():
            item = self.components[cid]
            if item["kind"] == "fan" and state["mode"] == "auto":
                state["commanded"] = int(self.sensors[item["sensor"]]["value"] > self.profile["threshold"])
            state["simulated"] = 0 if self._active("fan_failure", cid, tick) else state["commanded"]
        self.alerts = []
        for cid, sensor in self.sensors.items():
            if self.nodes[self.components[cid]["node"]] and sensor["value"] > self.profile["threshold"]:
                self.alerts.append({"rule": "gas_threshold", "target": cid})
        for cid, state in self.actuators.items():
            if self.nodes[self.components[cid]["node"]] and state["commanded"] != state["simulated"]:
                self.alerts.append({"rule": "actuator_mismatch", "target": cid})
        for node, online in self.nodes.items():
            if not online:
                self.alerts.append({"rule": "simulated_link_loss", "target": node})
                self.suppressed_messages += 1
                continue
            message = {
                "schema_version": "0.2-draft", "device_id": node,
                "boot_id": session_id(self.run_id, node), "sequence_number": tick,
                "timestamp": (START + timedelta(seconds=tick)).isoformat(),
                "sensors": {cid: {"measurement": "gas_signal", "unit": "normalized", "value": s["value"]}
                            for cid, s in self.sensors.items() if self.components[cid]["node"] == node},
                "actuators": {cid: deepcopy(s) for cid, s in self.actuators.items()
                              if self.components[cid]["node"] == node},
            }
            if len(self.history) == self.history.maxlen:
                self.evicted_messages += 1
            self.history.append(message)
            self.message_count += 1
        self.time += 1

    def snapshot(self):
        return {"time": self.time - 1, "nodes": dict(self.nodes),
                "sensors": {cid: {k: v for k, v in state.items() if k != "generator"} for cid, state in self.sensors.items()},
                "actuators": deepcopy(self.actuators), "alerts": deepcopy(self.alerts)}

    def export(self, code_version=None):
        return {
            "manifest": {"format": "edgeguard-house-run-v1", "model": self.VERSION,
                         "run_id": self.run_id, "source": "synthetic", "seed": self.seed,
                         "python_version": platform.python_version(),
                         "logical_start": START.isoformat(), "interval_seconds": 1,
                         "completed_steps": self.time, "node_count": self.node_count,
                         "extra_nodes": self.extra_nodes, "profile": deepcopy(self.profile),
                         "component_nodes": {cid: c["node"] for cid, c in self.components.items()},
                         "code_version": code_version, "message_count": self.message_count,
                         "evicted_messages": self.evicted_messages, "suppressed_messages": self.suppressed_messages},
            "actions": deepcopy(self.actions),
            "scenario_ground_truth": deepcopy(self.scenarios),
            "telemetry": list(self.history), "final_state": self.snapshot(),
        }

    @classmethod
    def replay(cls, exported):
        """Reproduce our own bounded simulator export; not physical telemetry replay."""
        m = exported["manifest"]
        if m["model"] != cls.VERSION or not 1 <= m["completed_steps"] <= cls.MAX_STEPS:
            raise ValueError("Unsupported replay.")
        if len(exported["actions"]) > cls.MAX_ACTIONS:
            raise ValueError("Too many actions.")
        sim = cls(m["seed"], m["node_count"], m["extra_nodes"], m["run_id"], m["profile"])
        actions = exported["actions"]
        if any(not 1 <= a["at_step"] <= m["completed_steps"] for a in actions):
            raise ValueError("Invalid action timing.")
        for tick in range(1, m["completed_steps"] + 1):
            for a in (a for a in actions if a["at_step"] == tick):
                if a["type"] == "command":
                    sim.command(a["target"], a["value"])
                elif a["type"] == "auto":
                    sim.auto_fan(a["target"])
                elif a["type"] == "scenario":
                    sim.inject(a["kind"], a["target"], a["end"] - a["start"])
                else:
                    raise ValueError("Unknown action type.")
            if tick < m["completed_steps"]:
                sim.step()
        return sim
