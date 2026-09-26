# Machine learning

No training or inference code exists yet. This area is reserved for workstation
preprocessing, training, evaluation and model export. Model binaries in models/
are ignored by Git. Compare simple rules with 2-3 selected ML methods first.

The implemented `python -m ml.gate_split` utility creates a reproducible session
split plan for the offline gate pilot. It groups all variants sharing a simulation
seed, including different usage profiles and suites. Training contains normal
sessions only; fault variants from training groups are explicitly excluded.
See the [Polish exercise](../docs/step-11-gate-pilot.md) for usage and limitations.
