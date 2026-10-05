"""Causal input histories and separately observed/censored command outcomes."""

from ml.gate_features import SAMPLE_MS, extract_features

RESPONSE_VERSION = "gate-command-response-1"


def _target(sent_ms, end_ms, reason=None, *, observed=False):
    duration = end_ms - sent_ms
    return {"observed": observed, "duration_ms": duration if observed else None,
            "follow_up_ms": duration, "censor_reason": reason}


def extract_response_examples(observations, events, *, history_samples=20):
    """Inputs end at command_sent; future results/readings only determine y.

    ACK is independently logged, so sensor gaps censor the contact target only.
    Physical confirmation is bounded by the first gap, opposite accepted target,
    or session end; a new same-target command does not erase an earlier request.
    IDs remain metadata and are never part of a feature row.
    """
    if type(history_samples) is not int or not 1 <= history_samples <= 200:
        raise ValueError("history_samples must be an integer in 1..200.")
    features = extract_features(observations, events)
    end = observations[-1]["logical_ms"]
    if events and events[-1]["logical_ms"] > end:
        raise ValueError("Events extend beyond the observed session.")
    times = [row["logical_ms"] for row in features]
    positions = {now: i for i, now in enumerate(times)}
    commands = [e for e in events if e["kind"] == "command_sent"]
    if len({e["logical_ms"] for e in commands}) != len(commands):
        raise ValueError("Response v1 requires distinct command send times.")
    by_id = {e["message"]["command_id"]: e for e in commands}
    results = {e["message"]["command_id"]: (i, e) for i, e in enumerate(events)
               if e["kind"] == "command_result"}
    gaps = [a + SAMPLE_MS for a, b in zip(times, times[1:]) if b != a + SAMPLE_MS]
    examples, excluded = [], []
    for command in commands:
        now, message = command["logical_ms"], command["message"]
        identity = {"command_id": message["command_id"], "prediction_ms": now}
        index = positions.get(now)
        reason = None
        if index is None or index + 1 < history_samples:
            reason = "missing_history"
        else:
            window = features[index - history_samples + 1:index + 1]
            input_times = [row["logical_ms"] for row in window]
            if input_times != list(range(now - (history_samples - 1) * SAMPLE_MS, now + 1, SAMPLE_MS)):
                reason = "gap_in_history"
        reply = results.get(message["command_id"])
        if reply is not None and reply[1]["logical_ms"] == now:
            reason = "instant_result"
        if reason:
            excluded.append({**identity, "reason": reason})
            continue
        limits = [(end, 2, "end_of_session")]
        gap = next((g for g in gaps if g > now), None)
        if gap is not None:
            limits.append((gap, 1, "sample_gap"))
        if reply is None:
            ack = {**_target(now, end, "end_of_session"), "accepted": None}
            contact = _target(now, min(t for t, _, _ in limits), "no_result")
        else:
            result_index, event = reply
            accepted = event["message"]["status"] == "accepted"
            ack = {**_target(now, event["logical_ms"], observed=True), "accepted": accepted}
            if not accepted:
                contact = _target(now, event["logical_ms"], "rejected")
            else:
                for other_index, other in results.values():
                    if (other_index > result_index and other["message"]["status"] == "accepted"
                            and by_id[other["message"]["command_id"]]["message"]["value"] != message["value"]):
                        limits.append((other["logical_ms"], 0, "superseded"))
                boundary, _, censor_reason = min(limits)
                contact = _target(now, boundary, censor_reason)
                key = "open_contact" if message["value"] == 110 else "closed_contact"
                for obs in observations[index:]:
                    tick = obs["logical_ms"]
                    if tick > boundary or tick == boundary and censor_reason != "end_of_session":
                        break
                    if tick >= event["logical_ms"] and obs[key]:
                        contact = _target(now, tick, observed=True)
                        break
        examples.append({**identity, "target_degrees": message["value"],
                         "input_times_ms": input_times,
                         "x": [dict(row["x"]) for row in window],
                         "y": {"ack": ack, "contact": contact}})
    return {"response_version": RESPONSE_VERSION, "examples": examples, "excluded": excluded}
