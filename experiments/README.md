# Experiments and thesis exports

No experiments have been run by this scaffold. The files in templates/ define
a handoff for future simulator and ML work.

For each real run preserve commit, configuration, seed (where applicable),
data source/version/checksum, model/features, timestamps and hardware.
The JSON template has null values and status template_not_executed.
Use completed only after execution and validation.

## CSV contract

Exact columns:

~~~text
run_id,method,f1,false_positive_rate,inference_ms,ram_mib
~~~

UTF-8, comma delimiters, decimal points. F1/FPR are fractions from 0 to 1,
inference latency is in milliseconds and RAM is in MiB.
Document aggregation, sample counts, evaluation unit, measurement method and
hardware in a manifest/report. Do not compare incompatible measurements.
Do not replace missing values with zeros.

With Python 3 installed, from the repository root:

~~~powershell
python scripts/export-thesis-results.py experiments/runs/RUN_ID/summary.csv
~~~

The header-only template deliberately cannot export a table: it has no results.
The script rejects malformed data, non-finite/out-of-range numbers and duplicate
run/method rows, and escapes LaTeX special characters.
It formats measurements; it does not verify scientific provenance.

Review data and output before committing thesis/generated/model-comparison.tex.
When publishing real results, include a sanitized source summary and manifest
alongside the table. Raw runs and datasets stay local with separate backups.
Unit-test numbers are synthetic fixtures, not thesis results.
