# Machine learning

No training or inference code exists yet. This area is reserved for workstation
preprocessing, training, evaluation and model export. Model binaries in models/
are ignored by Git. Compare simple rules with 2-3 selected ML methods first.

The implemented `python -m ml.gate_split` utility creates a reproducible session
split plan for the offline gate pilot. It groups all variants sharing a simulation
seed, including different usage profiles and suites. Training contains normal
sessions only; fault variants from training groups are explicitly excluded.
See the [Polish exercise](../docs/step-11-gate-pilot.md) for usage and limitations.

`ml.gate_features.extract_features` builds causal, unscaled numeric features
from one pilot session's observations and command events. It never reads ground
truth. Missing values remain null; no imputation or preprocessing is fitted.
Every call resets history, and prefix tests guard against future-data leakage.
This is an offline pilot adapter, not yet a live MQTT or Qt integration.

`python -m ml.gate_feature_export <split.json> --output <new-directory>` exports
the features per session into train/validation/test directories, preserving nulls
and provenance hashes. Follow [step 12](../docs/step-12-gate-features.md).

## Checklist before the first model comparison

- [x] Generate bounded gate sessions with legal usage profiles and controlled faults.
- [x] Keep related sessions together when splitting train/validation/test data.
- [x] Extract causal features, preserve missing values and record export provenance.
- [ ] Expand normal training data beyond the small observability pilot.
- [ ] Define observable fault intervals; configured session faults are not per-sample labels.
- [ ] Fit missing-value handling and any scaling on training data only.
- [ ] Compare temporal rules with Isolation Forest on the same held-out sessions.
- [ ] Choose thresholds on validation data; reserve the final test for reporting.
- [ ] Report false alarms, missed events and detection delays, including failures.

This checklist tracks the next offline experiment. Live Qt integration, physical
validation and Raspberry Pi measurements remain separate required steps in the
[research plan](../docs/ml-research-plan.md).
