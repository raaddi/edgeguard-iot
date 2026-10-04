import json

import numpy as np
import pytest

pytest.importorskip("torch")
from ml import gate_independent_calibration as experiment
from simulator.gate_pilot import simulate_session


def test_conditions_are_bounded_and_calibration_excludes_shifted_conditions():
    assert set(experiment.CALIBRATION_SEEDS).isdisjoint(experiment.EVALUATION_SEEDS)
    assert set(experiment.CALIBRATION_CONDITIONS) == {"cycles", "repeats", "idle"}
    assert experiment.CONDITIONS["slow"].stroke_bounds_ms == (1600, 2000)
    assert all(v.duration_ms == 30000 for v in experiment.CONDITIONS.values())


def test_scores_use_only_history_before_target_and_reset_each_session(monkeypatch):
    from ml.gate_residuals import ResidualScaler
    class Baselines:
        def scores(self, features):
            assert len(features) == 581
            return {"isolation_forest": [0.5] * len(features), "temporal_rules": [1.0] * len(features)}
    calls = []
    def predict(model, prep, x):
        calls.append(x.copy())
        return np.zeros((len(x), 3))
    monkeypatch.setattr(experiment, "forecast", predict)
    frozen = (None, None, Baselines(), {k: ResidualScaler((1, 1, 1)) for k in ("gru", "persistence")}, {})
    obs, events, _ = simulate_session(seed=1000, case="normal", run_id="alignment",
                                     settings=experiment.CONDITIONS["cycles"])
    result = experiment.score_session(frozen, obs, events)
    assert result["logical_ms"] == list(range(1000, 30001, 50))
    assert result["actual"][0][:2] == [1, 0]
    assert calls[0].shape == (581, 20, 20)
    index = experiment.FEATURE_NAMES.index("closed_contact")
    assert calls[0][0, -1, index] == obs[19]["closed_contact"]
    changed = [dict(o) for o in obs]
    changed[20]["closed_contact"] = False
    experiment.score_session(frozen, changed, events)
    np.testing.assert_array_equal(calls[0][0], calls[1][0])
    assert calls[0][1, -1, index] != calls[1][1, -1, index]


def test_thresholds_are_saved_before_evaluation_generation_and_shared_by_methods(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, "CALIBRATION_SEEDS", (1000,))
    monkeypatch.setattr(experiment, "EVALUATION_SEEDS", (2000,))
    monkeypatch.setattr(experiment, "load_frozen", lambda root: (None, None, None, None, {"frozen": "hash"}))
    def score(frozen, obs, events):
        times = [o["logical_ms"] for o in obs[20:]]
        actual = [[o[k] for k in experiment.TARGET_NAMES] for o in obs[20:]]
        return {"logical_ms": times, "scores": {k: [1.0] * len(times) for k in experiment.METHODS},
                "actual": actual, "predicted": actual, "pending_commands": [0] * len(times),
                "scaled_residuals": [[0, 0, 0] for t in times]}
    monkeypatch.setattr(experiment, "score_session", score)
    original = experiment.generate
    def generate(root, partition, *args):
        if partition == "evaluation":
            assert json.loads((root / "calibration.json").read_text())["normal_sessions"] == 3
        return original(root, partition, *args)
    monkeypatch.setattr(experiment, "generate", generate)
    output = tmp_path / "run"
    result = experiment.run_experiment(tmp_path, output)
    assert json.loads((output / "manifest.json").read_text())["status"] == "completed"
    for policy in experiment.POLICIES:
        assert result["thresholds"][policy] == {k: 1.0 for k in experiment.METHODS}
        for method in experiment.METHODS:
            assert len(result["policies"][policy][method]["sessions"]) == 20
            assert result["policies"][policy][method]["overall"]["normal_duration_ms"] == 145000
    assert len(list((output / "timelines" / "sample_max").glob("*.json"))) == 20
    with pytest.raises(FileExistsError):
        experiment.run_experiment(tmp_path, output)



def test_source_hash_mismatch_is_rejected_before_loading_joblib(tmp_path, monkeypatch):
    manifest = {"status": "completed", "experiment_version": "gate-alarms-1", "report_sha256": "wrong"}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "calibration.json").write_text("{}")
    (tmp_path / "report.json").write_text("{}")
    def forbidden(*args):
        pytest.fail("Unverified source must not load joblib")
    monkeypatch.setattr(experiment.joblib, "load", forbidden)
    with pytest.raises(ValueError, match="provenance"):
        experiment.load_frozen(tmp_path)
