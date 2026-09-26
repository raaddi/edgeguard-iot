"""Causal features for one offline gate session, never scenario ground truth."""

from collections import deque
import math
import re
from uuid import UUID

from contracts.commands import validate_command, validate_result

FEATURE_VERSION = "gate-features-1"
SAMPLE_MS = 50
MAX_SAMPLES = 10_000
MAX_EVENTS = 1000
OBS_KEYS = {"schema_version", "run_id", "device_id", "boot_id", "mechanism_id",
            "sequence_number", "logical_ms", "closed_contact", "open_contact", "current_a"}


def validate_inputs(observations, events):
    """Reject mixed sessions, unsorted data and unsupported pilot semantics."""
    if not 1 <= len(observations) <= MAX_SAMPLES or len(events) > MAX_EVENTS:
        raise ValueError("Expected one bounded session.")
    identity, previous = None, -1
    for obs in observations:
        if set(obs) != OBS_KEYS or obs["schema_version"] not in {"gate-pilot-0.1", "gate-pilot-0.2"}:
            raise ValueError("Unsupported observation fields/version.")
        for key in ("run_id", "device_id", "mechanism_id"):
            if not isinstance(obs[key], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", obs[key]):
                raise ValueError("Invalid observation identity.")
        if not isinstance(obs["boot_id"], str) or str(UUID(obs["boot_id"])) != obs["boot_id"]:
            raise ValueError("Invalid boot ID.")
        current_identity = tuple(obs[k] for k in ("schema_version", "run_id", "device_id", "boot_id", "mechanism_id"))
        if identity is not None and current_identity != identity:
            raise ValueError("Mixed sessions/sources.")
        identity = current_identity
        now, seq = obs["logical_ms"], obs["sequence_number"]
        if (type(now) is not int or type(seq) is not int or seq < 0
                or not previous < now <= 500_000 or now != seq * SAMPLE_MS):
            raise ValueError("Expected ordered samples on the pilot 50 ms grid.")
        previous = now
        if any(type(obs[k]) is not bool for k in ("closed_contact", "open_contact")):
            raise ValueError("Contacts must be boolean.")
        current = obs["current_a"]
        if current is not None and (type(current) not in (int, float)
                                    or not math.isfinite(current) or not 0 <= current <= 100):
            raise ValueError("Invalid pilot current.")
    sent, answered, source, previous = {}, set(), None, -1
    for event in events:
        if set(event) != {"logical_ms", "kind", "message"}:
            raise ValueError("Unsupported event fields.")
        now, message = event["logical_ms"], event["message"]
        if type(now) is not int or not 0 <= now <= 500_000 or now < previous:
            raise ValueError("Events must be ordered in logical time.")
        previous = now
        if event["kind"] == "command_sent":
            validate_command(message)
            if (message["operation"] != "set" or message["value"] not in (0, 110)
                    or message["component_id"] != "servo_01"
                    or message["observed_uptime_ms"] != now):
                raise ValueError("Unsupported pilot command.")
            key = (message["device_id"], message["target_boot_id"])
            if source is not None and key != source:
                raise ValueError("Mixed command sources.")
            source = key
            if message["command_id"] in sent:
                raise ValueError("Pilot command IDs must be unique.")
            sent[message["command_id"]] = message
        elif event["kind"] == "command_result":
            validate_result(message)
            command = sent.get(message["command_id"])
            if (command is None or message["command_id"] in answered
                    or message["handled_uptime_ms"] != now
                    or message["device_id"] != command["device_id"]
                    or message["boot_id"] != command["target_boot_id"]
                    or message["component_id"] != command["component_id"]):
                raise ValueError("Unmatched, duplicate or incompatible pilot result.")
            answered.add(message["command_id"])
        else:
            raise ValueError("Unknown event kind.")
    if source is not None and source[0] == observations[0]["device_id"] and source[1] != observations[0]["boot_id"]:
        raise ValueError("Feedback and commands disagree on the shared device boot.")


def extract_features(observations, events, *, window_ms=1000):
    """Window is (t-window_ms, t]; state resets at every function call.

    All events at t are applied before the sample at t, as in the pilot.
    No sorting, backfill, normalization, labels, IDs or future values enter x.
    """
    if type(window_ms) is not int or not 50 <= window_ms <= 60_000 or window_ms % SAMPLE_MS:
        raise ValueError("window_ms must be a multiple of 50 in 50..60000.")
    validate_inputs(observations, events)
    history, commands = deque(), deque()
    pending, index, output = {}, 0, []
    latest_command = latest_result = accepted = contact_delay = None
    previous = None
    for obs in observations:
        now = obs["logical_ms"]
        while index < len(events) and events[index]["logical_ms"] <= now:
            event = events[index]
            message, event_ms = event["message"], event["logical_ms"]
            if event["kind"] == "command_sent":
                pending[message["command_id"]] = event
                latest_command = event
                commands.append(event_ms)
            else:
                command = pending.pop(message["command_id"])
                latest_result = (event_ms - command["logical_ms"], message["status"] == "accepted")
                if message["status"] == "accepted":
                    accepted = (event_ms, command["message"]["value"])
                    contact_delay = None
            index += 1
        if accepted is not None and contact_delay is None:
            target_contact = "open_contact" if accepted[1] == 110 else "closed_contact"
            if obs[target_contact]:
                contact_delay = now - accepted[0]
        # A transition is counted only between adjacent available samples.
        contiguous = previous is not None and now - previous["logical_ms"] == SAMPLE_MS
        transitions = sum(obs[k] != previous[k] for k in ("open_contact", "closed_contact")) if contiguous else 0
        history.append((obs, transitions))
        while history and history[0][0]["logical_ms"] <= now - window_ms:
            history.popleft()
        while commands and commands[0] <= now - window_ms:
            commands.popleft()
        currents = [o["current_a"] for o, _ in history if o["current_a"] is not None]
        expected = min(window_ms // SAMPLE_MS, now // SAMPLE_MS + 1)
        features = {
            "closed_contact": int(obs["closed_contact"]),
            "open_contact": int(obs["open_contact"]),
            "current_a": obs["current_a"],
            "current_missing": int(obs["current_a"] is None),
            "current_mean_a": sum(currents) / len(currents) if currents else None,
            "current_max_a": max(currents) if currents else None,
            "current_available_fraction": len(currents) / expected,
            "sample_coverage": len(history) / expected,
            "history_span_ms": min(now, window_ms - SAMPLE_MS),
            "sample_gap_ms": now - previous["logical_ms"] if previous else None,
            "contact_transitions": sum(n for _, n in history),
            "commands_in_window": len(commands),
            "pending_commands": len(pending),
            "last_command_degrees": latest_command["message"]["value"] if latest_command else None,
            "command_age_ms": now - latest_command["logical_ms"] if latest_command else None,
            "last_result_delay_ms": latest_result[0] if latest_result else None,
            "last_result_accepted": int(latest_result[1]) if latest_result else None,
            "accepted_target_degrees": accepted[1] if accepted else None,
            "accepted_target_age_ms": now - accepted[0] if accepted else None,
            "target_contact_delay_ms": contact_delay,
        }
        output.append({"logical_ms": now, "x": features})
        previous = obs
    return output
