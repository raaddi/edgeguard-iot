import json

import pytest

from contracts.commands import validate_command, validate_result
from contracts.telemetry import TelemetryError, validate_telemetry
from simulator import gate_pilot as pilot


def test_paired_runs_expose_different_observations_without_truth_leakage():
    summaries, truths = {}, []
    for case in pilot.CASES:
        args = dict(seed=42, case=case, run_id="test", feedback_device_id="other_node")
        observations, events, truth = pilot.simulate_session(**args)
        assert (observations, events, truth) == pilot.simulate_session(**args)
        assert len(observations) == 161
        assert [o["logical_ms"] for o in observations] == list(range(0, 8001, 50))
        expected = {"schema_version", "run_id", "device_id", "boot_id", "mechanism_id",
                    "sequence_number", "logical_ms", "closed_contact", "open_contact", "current_a"}
        assert all(set(o) == expected and o["device_id"] == "other_node" for o in observations)
        assert len(events) == 4
        for e in events:
            (validate_command if e["kind"] == "command_sent" else validate_result)(e["message"])
            assert e["message"]["device_id"] == "virtual_gate_01"
        with pytest.raises(TelemetryError):
            validate_telemetry(observations[0])  # Pilot format is deliberately not MQTT 1.0.
        summaries[case] = pilot.summarize(observations, events)
        truths.append(truth)
    assert len({t["config"]["stroke_ms"] for t in truths}) == 1
    assert len({t["paired_group"] for t in truths}) == 1
    assert summaries["normal"]["open_contact_seen_before_close"]
    assert summaries["command_delay"]["result_delays_ms"] == [1200, 1200]
    assert max(summaries["normal"]["result_delays_ms"]) <= 150
    for case in ("motion_stall", "open_contact_stuck_low"):
        assert not summaries[case]["open_contact_seen_before_close"]
    assert summaries["motion_stall"]["peak_current_a"] > 0.6
    assert all(s["final_closed_contact"] for s in summaries.values())


def test_result_is_recorded_before_motion_finishes_and_null_is_not_zero():
    observations, events, _ = pilot.simulate_session(seed=9, case="normal", run_id="t",
                                                    measure_current=False)
    accepted = next(e for e in events if e["kind"] == "command_result")
    sample = next(o for o in observations if o["logical_ms"] == accepted["logical_ms"])
    assert not sample["open_contact"]
    assert all(o["current_a"] is None for o in observations)
    assert pilot.summarize(observations, events)["peak_current_a"] is None


def test_artifacts_are_complete_and_never_overwritten(tmp_path):
    root = pilot.run_suite(output=tmp_path, suite_id="one", sessions_per_case=1)
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["status"] == "completed" and len(manifest["sessions"]) == 4
    original = (root / "manifest.json").read_bytes()
    for session in manifest["sessions"]:
        folder = root / session["run_id"]
        truth = json.loads((folder / "ground_truth.json").read_text())
        obs = [json.loads(s) for s in (folder / "observations.jsonl").read_text().splitlines()]
        events = [json.loads(s) for s in (folder / "events.jsonl").read_text().splitlines()]
        expected = pilot.simulate_session(
            seed=truth["seed"], case=truth["case"], run_id=session["run_id"])
        assert [obs, events, truth] == json.loads(json.dumps(expected))
        assert json.loads((folder / "summary.json").read_text()) == pilot.summarize(obs, events)
    with pytest.raises(FileExistsError):
        pilot.run_suite(output=tmp_path, suite_id="one", sessions_per_case=1)
    assert (root / "manifest.json").read_bytes() == original


def test_failed_run_is_marked(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("test write failure")
    monkeypatch.setattr(pilot, "_jsonl", fail)
    with pytest.raises(OSError):
        pilot.run_suite(output=tmp_path, suite_id="failed", sessions_per_case=1)
    assert json.loads((tmp_path / "failed" / "manifest.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("kwargs", [{"sessions_per_case": 0}, {"sessions_per_case": 26},
                                     {"seed": -1}, {"seed": 2**32 - 1},
                                     {"measure_current": 1}, {"device_id": "../x"},
                                     {"suite_id": "../escape"}])
def test_invalid_suite_config_creates_no_files(tmp_path, kwargs):
    with pytest.raises((ValueError, pilot.argparse.ArgumentTypeError)):
        pilot.run_suite(output=tmp_path, **kwargs)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("profile", pilot.PROFILES)
def test_legal_profiles_are_repeatable_and_separate_from_features(profile):
    args = dict(seed=42, case="normal", run_id="profile-test", profile=profile)
    obs, events, truth = pilot.simulate_session(**args)
    assert (obs, events, truth) == pilot.simulate_session(**args)
    commands = [e for e in events if e["kind"] == "command_sent"]
    assert [(e["logical_ms"], e["message"]["value"]) for e in commands] == list(pilot.PROFILES[profile])
    assert all("profile" not in o for o in obs)
    assert obs[-1]["closed_contact"]
    summary = pilot.summarize(obs, events)
    assert summary["open_contact_seen_before_close"] == {
        "standard": True, "repeat_open": True, "early_return": False, "idle": None,
    }[profile]
    if profile == "idle":
        assert not events and all(o["closed_contact"] for o in obs)
    if profile == "early_return":
        assert any(o["open_contact"] for o in obs if o["logical_ms"] > 3000)


def test_profile_is_persisted_and_unknown_profile_rejected(tmp_path):
    root = pilot.run_suite(output=tmp_path, sessions_per_case=1, profile="repeat_open")
    manifest = json.loads((root / "manifest.json").read_text())
    assert manifest["profile"] == "repeat_open"
    assert manifest["schedule_ms_degrees"] == [[1000, 110], [1500, 110], [5000, 0]]
    for entry in manifest["sessions"]:
        truth = json.loads((root / entry["run_id"] / "ground_truth.json").read_text())
        assert truth["profile"] == "repeat_open"
    with pytest.raises(ValueError):
        pilot.run_suite(output=tmp_path, suite_id="invalid", profile="unknown")
    assert not (tmp_path / "invalid").exists()
