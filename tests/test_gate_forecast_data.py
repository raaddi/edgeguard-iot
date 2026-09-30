from dataclasses import asdict
import hashlib
import json

import numpy as np
import pytest

from ml.gate_forecast_data import FEATURE_NAMES, ForecastPreprocessor, SequenceDataset, normal_arrays
from ml.gate_sequence_export import export_sequences
from ml.gate_split import load_sessions, split_sessions
from simulator.gate_pilot import run_suite


@pytest.fixture
def dataset_root(tmp_path):
    suite = run_suite(output=tmp_path, suite_id="pilot")
    plan = split_sessions(load_sessions([suite]))
    split = tmp_path / "split.json"
    split.write_text(json.dumps(plan), encoding="utf-8")
    root = tmp_path / "sequences"
    export_sequences(split, root)
    return root


def test_loader_preserves_order_and_never_reads_unrequested_partition(dataset_root):
    dataset = SequenceDataset(dataset_root)
    for path in (dataset_root / "test").glob("*.jsonl"):
        path.write_text("test must not be read during training", encoding="utf-8")
    x, y = normal_arrays(dataset, "train")
    assert x.shape == (141, 20, 20) and y.shape == (141, 3)
    assert np.isnan(x[0, :, FEATURE_NAMES.index("last_command_degrees")]).all()
    assert len(list(dataset.sessions("validation", normal_only=True))) == 1
    with pytest.raises(ValueError, match="hash"):
        list(dataset.sessions("test"))


@pytest.mark.parametrize("change", ["timing", "extra_feature"])
def test_rehashed_invalid_schema_still_rejected(dataset_root, change):
    manifest_path = dataset_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entry = next(s for s in manifest["sessions"] if s["partition"] == "train")
    path = dataset_root / "train" / (entry["run_id"] + ".jsonl")
    rows = path.read_text().splitlines()
    row = json.loads(rows[0])
    if change == "timing":
        row["target_ms"] = row["prediction_ms"]
    else:
        row["x"][0]["case"] = 1
    rows[0] = json.dumps(row)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    entry["sequences_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        normal_arrays(SequenceDataset(dataset_root), "train")


def test_preprocessing_is_train_only_finite_and_roundtrips_with_missing_channel():
    x = np.zeros((2, 3, 20), dtype=np.float32)
    x[:, :, 0] = np.array([1, 3])[:, None]
    x[:, :, 1] = np.nan
    y = np.array([[0, 1, np.nan], [1, 0, np.nan]], dtype=np.float32)
    prep = ForecastPreprocessor.fit(x, y)
    before = asdict(prep)
    later = x.copy()
    later[:, :, 0] = 1000
    transformed = prep.transform(later)
    assert transformed.shape == (2, 3, 40) and np.isfinite(transformed).all()
    assert transformed[0, 0, 0] == 998  # Training mean=2, std=1, not refit on 1000.
    assert transformed[:, :, 21].all() and prep.median[1] == 0
    assert asdict(prep) == before
    restored = ForecastPreprocessor(**json.loads(json.dumps(before)))
    np.testing.assert_array_equal(restored.transform(x), prep.transform(x))
    targets, mask = restored.targets(y)
    assert not mask[:, 2].any() and not prep.current_enabled
    assert np.isfinite(targets).all() and (targets[:, 2] == 0).all()
