import csv
from copy import deepcopy
import pytest
from simulator.desktop.archive import measurements_csv, read_archive, restore_archive
from simulator.house import HouseSimulation


def test_replay_restores_all_data_and_csv_only_measurements(tmp_path):
    sim = HouseSimulation(node_count=1, extra_nodes=2)
    sim.inject("sensor_freeze", "virtual_gas_02", 3)
    sim.step()
    sim.command("servo_06", 110)
    archive = sim.export({"commit": "test", "working_tree_dirty": False})
    assert restore_archive(archive).snapshot() == sim.snapshot()
    path = tmp_path / "measurements.csv"
    measurements_csv(sim, path)
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 12
    assert set(rows[0]) == {"device_id", "sequence_number", "timestamp", "sensor_id", "value", "unit"}


@pytest.mark.parametrize("mutation", [
    lambda d: d["manifest"].update(completed_steps=10001),
    lambda d: d["manifest"].update(node_count=100000),
    lambda d: d["manifest"].update(seed=True),
    lambda d: d["manifest"].update(run_id="../unexpected"),
    lambda d: d["manifest"]["profile"].update(threshold=0.5),
    lambda d: d["final_state"]["nodes"].update(esp32_node_01=False),
    lambda d: d["telemetry"][0]["sensors"]["gas_03"].update(value=0.8),
    lambda d: d.update(actions=[{"at_step": "bad"}]),
])
def test_replay_rejects_corruption_before_installing_session(mutation):
    data = deepcopy(HouseSimulation().export())
    mutation(data)
    with pytest.raises(ValueError):
        restore_archive(data)


def test_archive_size_is_bounded(tmp_path, monkeypatch):
    import simulator.desktop.archive as archive
    monkeypatch.setattr(archive, "MAX_ARCHIVE_BYTES", 32)
    path = tmp_path / "large.json"
    path.write_bytes(b" " * 33)
    with pytest.raises(ValueError, match="limit"):
        read_archive(path)
