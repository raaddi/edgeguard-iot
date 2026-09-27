"""Pilot-only counterfactual labels and explicit event evaluation protocol."""

from ml.gate_features import SAMPLE_MS, validate_inputs

LABEL_VERSION = "gate-counterfactual-1"
EVALUATION_VERSION = "gate-events-1"


def _states(observations, events):
    pending, target, index = set(), None, 0
    for obs in observations:
        while index < len(events) and events[index]["logical_ms"] <= obs["logical_ms"]:
            event = events[index]
            message = event["message"]
            if event["kind"] == "command_sent":
                pending.add(message["command_id"])
            else:
                pending.remove(message["command_id"])
                if message["status"] == "accepted":
                    # Commands are unique and the bounded pilot preserves order.
                    command = next(e["message"] for e in events[:index]
                                   if e["kind"] == "command_sent"
                                   and e["message"]["command_id"] == message["command_id"])
                    target = command["value"]
            index += 1
        yield (len(pending), target, obs["closed_contact"], obs["open_contact"], obs["current_a"])


def counterfactual_labels(observations, events, reference_observations, reference_events):
    """Label differences from the paired fault-free run, never detector scores.

    Valid only for this deterministic simulator with identical seed, profile,
    noise draws and sampling. These are observable-divergence labels, not
    physical fault-onset labels and not available to a deployed detector.
    """
    validate_inputs(observations, events)
    validate_inputs(reference_observations, reference_events)
    times = [o["logical_ms"] for o in observations]
    if times != [o["logical_ms"] for o in reference_observations]:
        raise ValueError("Counterfactual samples must be aligned.")
    if times != list(range(0, times[-1] + SAMPLE_MS, SAMPLE_MS)):
        raise ValueError("Evaluation requires complete sampling from time zero.")
    def schedule(rows):
        return [(e["logical_ms"], e["message"]["value"])
                for e in rows if e["kind"] == "command_sent"]
    if schedule(events) != schedule(reference_events):
        raise ValueError("Counterfactual commands must match.")
    return [a != b for a, b in zip(_states(observations, events),
                                  _states(reference_observations, reference_events))]


def intervals(flags):
    """Half-open index intervals; no point adjustment or merging across gaps."""
    result, start = [], None
    for index, flag in enumerate([*flags, False]):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            result.append((start, index))
            start = None
    return result


def alarms(scores, threshold, *, persistence=3):
    """Alarm becomes active on the third high sample, never backdated."""
    result, count = [], 0
    for score in scores:
        count = count + 1 if score > threshold else 0
        result.append(count >= persistence)
    return result


def evaluate(records):
    """One alarm start can match one truth interval; an early alarm is false.

    Each record contains aligned labels/alarms for an entire 50 ms session.
    Normal exposure uses only fault-free sessions; all unmatched alarms are
    additionally counted, including alarms in fault-configured sessions.
    """
    counts = dict(events=0, detected_events=0, missed_events=0, alarms=0,
                  unmatched_alarms=0, normal_alarms=0, normal_duration_ms=0,
                  negative_samples=0, false_positive_samples=0)
    delays = []
    for record in records:
        truth, predicted = record["labels"], record["alarms"]
        if not truth or len(truth) != len(predicted):
            raise ValueError("Labels and alarms must be nonempty and aligned.")
        events = intervals(truth)
        starts = [a for a, _ in intervals(predicted)]
        matched = set()
        for start in starts:
            match = next((i for i, (a, b) in enumerate(events)
                          if i not in matched and a <= start < b), None)
            if match is None:
                counts["unmatched_alarms"] += 1
            else:
                matched.add(match)
                delays.append((start - events[match][0]) * SAMPLE_MS)
        counts["events"] += len(events)
        counts["detected_events"] += len(matched)
        counts["missed_events"] += len(events) - len(matched)
        counts["alarms"] += len(starts)
        counts["negative_samples"] += sum(not x for x in truth)
        counts["false_positive_samples"] += sum(p and not y for p, y in zip(predicted, truth))
        if record["normal"]:
            if any(truth):
                raise ValueError("Fault-free reference unexpectedly has positive labels.")
            counts["normal_alarms"] += len(starts)
            counts["normal_duration_ms"] += (len(truth) - 1) * SAMPLE_MS
    def ratio(a, b):
        return a / b if b else None
    return {**counts,
            "event_recall": ratio(counts["detected_events"], counts["events"]),
            "event_precision": ratio(counts["detected_events"], counts["alarms"]),
            "false_alarms_per_normal_hour": ratio(counts["normal_alarms"] * 3_600_000,
                                                  counts["normal_duration_ms"]),
            "sample_fpr": ratio(counts["false_positive_samples"], counts["negative_samples"]),
            "detection_delays_ms": delays}
