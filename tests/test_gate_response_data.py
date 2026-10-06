import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from ml import gate_response_data as loader
from ml import gate_response_export as exporter
from ml.gate_forecast_data import FEATURE_NAMES


@pytest.fixture(scope="module")
def exported_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("response-data") / "export"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(exporter, "ROLE_SEEDS", {
            "train": (3000,), "selection": (4000,),
            "calibration": (5000,), "evaluation": (6000,),
        })
        exporter.export_responses(root)
    return root


@pytest.fixture
def dataset_root(tmp_path, exported_root):
    root = tmp_path / "responses"
    shutil.copytree(exported_root, root)
    return root


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


def train_entry(manifest):
    return next(e for e in manifest["sessions"] if e["role"] == "train" and e["condition"] == "cycles")


def test_role_access_is_lazy_and_never_decodes_ground_truth(dataset_root, monkeypatch):
    opened = []
    original = loader._read
    def tracked_read(path):
        opened.append(Path(path).relative_to(dataset_root))
        return original(path)
    monkeypatch.setattr(loader, "_read", tracked_read)
    dataset = loader.ResponseDataset(dataset_root)
    assert opened == [Path("manifest.json"), Path("protocol.md"), Path("report.json")]
    # Hashing preserves provenance without exposing truth as parsed model input.
    decoder = loader._json
    def no_truth(raw):
        assert b'"delivery_delay_ms"' not in raw
        assert b'"config"' not in raw
        return decoder(raw)
    monkeypatch.setattr(loader, "_json", no_truth)
    sessions = list(dataset.sessions("train"))
    assert len(sessions) == 3
    assert all("train" in path.parts for path in opened[3:])
    assert all(entry["case"] == "normal" for entry, *_ in sessions)
    for entry in dataset.manifest["sessions"]:
        if entry["role"] == "evaluation":
            (dataset_root / entry["examples_file"]).write_text("evaluation has not been opened", encoding="utf-8")
    x, y, follow_up = loader.response_arrays(dataset.sessions("train"))
    assert x.shape == (10, 20, 20) and y.shape == follow_up.shape == (10, 2)
    assert x.dtype == y.dtype == follow_up.dtype == np.float32
    assert np.isfinite(y).all() and (follow_up == y).all()
    np.testing.assert_array_equal(x[0, -1, FEATURE_NAMES.index("last_command_degrees")], 110)
    with pytest.raises(ValueError, match="hash"):
        list(dataset.sessions("evaluation"))


def test_idle_sessions_and_censored_targets_remain_explicit(dataset_root):
    dataset = loader.ResponseDataset(dataset_root)
    train = list(dataset.sessions("train"))
    idle = [batch for batch in train if batch[0]["condition"] == "idle"]
    x, y, follow_up = loader.response_arrays(idle)
    assert x.shape == (0, 20, 20) and y.shape == follow_up.shape == (0, 2)
    sensor_x, sensor_y = loader.sensor_arrays(idle)
    assert sensor_x.shape == (581, 20, 20) and sensor_y.shape == (581, 3)
    assert sensor_x.dtype == sensor_y.dtype == np.float32
    np.testing.assert_array_equal(sensor_y[:, 0], 1)
    sensor_x, sensor_y = loader.sensor_arrays(train)
    assert sensor_x.shape == (1743, 20, 20) and sensor_y.shape == (1743, 3)
    evaluation = list(dataset.sessions("evaluation"))
    x, y, follow_up = loader.response_arrays(evaluation)
    assert x.shape == (92, 20, 20) and y.shape == follow_up.shape == (92, 2)
    assert np.isfinite(y[:, 0]).all() and np.isnan(y[:, 1]).any()
    assert np.isfinite(follow_up).all() and (follow_up >= 0).all()
    assert {row["y"]["contact"]["censor_reason"] for _, _, _, data in evaluation
            for row in data["examples"] if not row["y"]["contact"]["observed"]} == {"superseded"}
    with pytest.raises(ValueError, match="role"):
        list(dataset.sessions("test"))


@pytest.mark.parametrize("change", ["status", "version", "history", "overlap", "historical",
                                   "assignment", "case", "condition", "conditions", "missing",
                                   "duplicate", "total", "count", "path", "hash", "provenance"])
def test_inconsistent_manifest_rejected_before_opening_any_session(dataset_root, monkeypatch, change):
    path = dataset_root / "manifest.json"
    manifest = read(path)
    entry = train_entry(manifest)
    if change == "status":
        manifest["status"] = "failed"
    elif change == "version":
        manifest["response_version"] = "unknown"
    elif change == "history":
        manifest["history_samples"] = 20.0
    elif change == "overlap":
        manifest["seed_roles"]["selection"] = [3000]
    elif change == "historical":
        manifest["seed_roles"]["train"] = [42]
    elif change == "assignment":
        manifest["group_assignments"]["3000"] = "evaluation"
    elif change == "case":
        entry["case"] = "motion_stall"
    elif change == "condition":
        manifest["role_conditions"]["train"].append("slow")
    elif change == "conditions":
        manifest["conditions"]["cycles"]["duration_ms"] = 30000.0
    elif change == "missing":
        manifest["sessions"].pop()
    elif change == "duplicate":
        manifest["sessions"][1] = dict(entry)
    elif change == "total":
        manifest["examples"] += 1
    elif change == "count":
        entry["commands"] = True
    elif change == "path":
        entry["examples_file"] = "../outside.json"
    elif change == "hash":
        entry["examples_sha256"] = "z" * 64
    elif change == "provenance":
        manifest["historical_seeds_excluded"].pop()
    save(path, manifest)
    original = loader._read
    def only_manifest(file):
        assert Path(file).name == "manifest.json"
        return original(file)
    monkeypatch.setattr(loader, "_read", only_manifest)
    with pytest.raises(ValueError):
        loader.ResponseDataset(dataset_root)


@pytest.mark.parametrize("change", ["timing", "feature", "duration", "bool_type", "float_type"])
def test_rehashed_targets_must_equal_causal_recomputation(dataset_root, change):
    manifest_path = dataset_root / "manifest.json"
    manifest = read(manifest_path)
    entry = train_entry(manifest)
    path = dataset_root / entry["examples_file"]
    data = read(path)
    row = data["examples"][0]
    if change == "timing":
        row["prediction_ms"] += 50
    elif change == "feature":
        row["x"][0]["case"] = 1
    elif change == "duration":
        row["y"]["contact"]["duration_ms"] += 50
    elif change == "bool_type":
        row["y"]["ack"]["observed"] = 1
    elif change == "float_type":
        row["prediction_ms"] = float(row["prediction_ms"])
    save(path, data)
    entry["examples_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    save(manifest_path, manifest)
    with pytest.raises(ValueError, match="causal"):
        list(loader.ResponseDataset(dataset_root).sessions("train"))


@pytest.mark.parametrize("file", ["observations", "events", "ground_truth", "examples"])
def test_requested_role_checks_each_recorded_hash(dataset_root, file):
    entry = train_entry(read(dataset_root / "manifest.json"))
    path = dataset_root / entry[file + "_file"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash"):
        list(loader.ResponseDataset(dataset_root).sessions("train"))


def test_session_identity_still_checked_after_hash_is_rewritten(dataset_root):
    manifest_path = dataset_root / "manifest.json"
    manifest = read(manifest_path)
    entry = train_entry(manifest)
    path = dataset_root / entry["observations_file"]
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["run_id"] = "another-session"
    lines[0] = json.dumps(first)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    entry["observations_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    save(manifest_path, manifest)
    with pytest.raises(ValueError, match="identity"):
        list(loader.ResponseDataset(dataset_root).sessions("train"))


def test_input_size_and_json_recursion_have_explicit_bounds(dataset_root, tmp_path):
    entry = train_entry(read(dataset_root / "manifest.json"))
    (dataset_root / entry["examples_file"]).write_bytes(b" " * (loader.MAX_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="4 MiB"):
        list(loader.ResponseDataset(dataset_root).sessions("train"))
    root = tmp_path / "deep"
    root.mkdir()
    (root / "manifest.json").write_text("[" * 20000 + "]" * 20000, encoding="utf-8")
    with pytest.raises(ValueError, match="JSON|manifest"):
        loader.ResponseDataset(root)


def test_rehashed_raw_duration_must_still_match_frozen_condition(dataset_root):
    manifest_path = dataset_root / "manifest.json"
    manifest = read(manifest_path)
    entry = train_entry(manifest)
    path = dataset_root / entry["observations_file"]
    lines = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[-1])
    row["logical_ms"] += 50
    row["sequence_number"] += 1
    lines[-1] = json.dumps(row)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    entry["observations_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    save(manifest_path, manifest)
    with pytest.raises(ValueError, match="timing"):
        list(loader.ResponseDataset(dataset_root).sessions("train"))


@pytest.mark.parametrize("file", ["protocol.md", "report.json"])
def test_source_provenance_hashes_are_checked_without_decoding_evaluation(dataset_root, file):
    path = dataset_root / file
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="provenance hash"):
        loader.ResponseDataset(dataset_root)
