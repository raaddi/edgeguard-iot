"""Convert reviewed experiment CSV to a LaTeX table; standard library only.

This is a formatting bridge, not a simulator, evaluator or evidence validator.
Default output: thesis/generated/model-comparison.tex.
"""
import argparse
import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ("run_id", "method", "f1", "false_positive_rate", "inference_ms", "ram_mib")


def tex_escape(value):
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def export_table(source, destination):
    with Path(source).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(COLUMNS):
            raise ValueError("CSV columns must be: " + ",".join(COLUMNS))
        rows = list(reader)
    if not rows:
        raise ValueError("No measurements: a header-only template is not a result.")
    rendered = []
    identities = set()
    for line, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Line {line}: incorrect number of columns.")
        run_id, method = row["run_id"].strip(), row["method"].strip()
        if not run_id or not method:
            raise ValueError(f"Line {line}: run_id and method are required.")
        if any(ord(char) < 32 for char in run_id + method):
            raise ValueError(f"Line {line}: control characters are not allowed.")
        if (run_id, method) in identities:
            raise ValueError(f"Line {line}: duplicate run_id/method.")
        identities.add((run_id, method))
        values = []
        for column in COLUMNS[2:]:
            try:
                value = float(row[column])
            except ValueError as exc:
                raise ValueError(f"Line {line}: {column} must be numeric.") from exc
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Line {line}: {column} must be finite and non-negative.")
            if column in ("f1", "false_positive_rate") and value > 1:
                raise ValueError(f"Line {line}: {column} must be between 0 and 1.")
            values.append(value)
        rendered.append(
            tex_escape(run_id) + " / " + tex_escape(method) + " & "
            + " & ".join(f"{v:.3f}" if i < 2 else f"{v:.2f}"
                         for i, v in enumerate(values)) + r" \\"
        )
    content = "\n".join([
        "% Generated from reviewed measurements. Do not edit numbers by hand.",
        r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{5cm}rrrr@{}}",
        r"\caption{Zestawienie wyeksportowanych pomiarów; interpretację i warunki podano w tekście.}\label{tab:model-comparison}\\",
        r"\toprule",
        r"Przebieg / metoda & F1 & FPR & Inferencja [ms] & RAM [MiB] \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"Przebieg / metoda & F1 & FPR & Inferencja [ms] & RAM [MiB] \\",
        r"\midrule",
        r"\endhead",
        *rendered,
        r"\bottomrule",
        r"\end{longtable}",
        "",
    ])
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "thesis/generated/model-comparison.tex")
    args = parser.parse_args()
    try:
        export_table(args.csv_file, args.output)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Export failed: {exc}\n")
    print(f"Written: {args.output}")


if __name__ == "__main__":
    main()
