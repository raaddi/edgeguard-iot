# Machine learning

Offline workstation training and evaluation now compare Isolation Forest with
temporal/current rules on the synthetic gate pilot. Live inference in Qt or on
Raspberry Pi is not implemented. Generated datasets and model binaries stay out
of Git. Run `python -m ml.gate_experiment` after installing requirements-ml.txt;
see [step 13](../docs/step-13-first-ml.md) for the protocol and limitations.

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

`ml.gate_sequences.iter_sequences` prepares per-session forecast examples with
20 history samples and a separate future sensor target. It preserves nulls and
excludes windows spanning missing samples. See [step 14](../docs/step-14-gate-sequences.md)
for timing, leakage protections and the planned persistence/GRU comparison.

## Checklist before the first model comparison

- [x] Generate bounded gate sessions with legal usage profiles and controlled faults.
- [x] Keep related sessions together when splitting train/validation/test data.
- [x] Extract causal features, preserve missing values and record export provenance.
- [x] Expand the pilot to four profiles and 20 seed groups (still not representative real data).
- [x] Define synthetic observable-divergence intervals using paired fault-free runs.
- [x] Fit missing-value handling on training data only; no scaling needed for this baseline.
- [x] Compare temporal rules with Isolation Forest on the same held-out sessions.
- [x] Choose thresholds on normal validation data before reading the pilot test.
- [x] Report false alarms, missed events and detection delays, including failures.
- [ ] Expand parameter families and hold out unseen usage conditions.
- [ ] Study sequential prediction and compare under a predefined alarm budget.

This checklist tracks the next offline experiment. Live Qt integration, physical
validation and Raspberry Pi measurements remain separate required steps in the
[research plan](../docs/ml-research-plan.md).
