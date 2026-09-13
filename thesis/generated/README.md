# Reviewed experiment exports

The results chapter conditionally includes `model-comparison.tex`.
There is no table until actual results are exported.

From the repository root, with Python 3 installed:

```powershell
python scripts/export-thesis-results.py experiments/runs/RUN_ID/summary.csv
```

Input columns are documented in `experiments/README.md`.
Review the source measurements and generated diff before committing an export.
No simulator or ML measurements have been performed by this scaffold.
