"""Bounded import/export of this laboratory's reproducible experiments."""

import csv
import argparse
import json
from pathlib import Path
from simulator.__main__ import identifier
from simulator.house import HouseSimulation, load_profile

MAX_ARCHIVE_BYTES = 16 * 1024 * 1024


def measurements_csv(sim, path):
    with Path(path).open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["device_id", "sequence_number", "timestamp", "sensor_id", "value", "unit"])
        for message in sim.history:
            for cid, sensor in message["sensors"].items():
                writer.writerow([message["device_id"], message["sequence_number"], message["timestamp"], cid, sensor["value"], sensor["unit"]])


def read_archive(path):
    with Path(path).open("rb") as source:
        raw = source.read(MAX_ARCHIVE_BYTES + 1)
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("Plik przekracza limit 16 MB.")
    return json.loads(raw.decode("utf-8"))


def restore_archive(data):
    """Rebuild before installing a new UI session; never trust file final_state."""
    try:
        manifest = data["manifest"]
        if manifest["format"] != "edgeguard-house-run-v1" or manifest["profile"] != load_profile():
            raise ValueError("Nieobsługiwany format lub profil makiety.")
        for key, low, high in [("node_count", 1, 3), ("extra_nodes", 0, 9),
                               ("completed_steps", 1, HouseSimulation.MAX_STEPS),
                               ("seed", 0, 2**31 - 1)]:
            value = manifest[key]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"Nieprawidłowa wartość {key}.")
        identifier(manifest["run_id"])
        actions = data["actions"]
        if not isinstance(actions, list) or len(actions) > HouseSimulation.MAX_ACTIONS:
            raise ValueError("Nieprawidłowa liczba działań.")
        ticks = [a["at_step"] for a in actions]
        if any(type(t) is not int for t in ticks) or ticks != sorted(ticks):
            raise ValueError("Nieprawidłowa kolejność działań.")
        rebuilt = HouseSimulation.replay(data)
        expected = rebuilt.export(manifest["code_version"])
        # Runtime version can differ; verify all model data, including the full manifest.
        expected["manifest"]["python_version"] = manifest["python_version"]
        if expected != data:
            raise ValueError("Dane pliku różnią się od odtworzonego przebiegu. Nie wczytano sesji.")
        return rebuilt
    except (KeyError, TypeError, AttributeError, OverflowError, argparse.ArgumentTypeError) as error:
        raise ValueError("Nieprawidłowy plik eksperymentu.") from error
