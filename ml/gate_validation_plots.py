"""Render validation evidence on shared time axes (headless PNG export)."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ml.gate_evaluation import intervals


def plot_timeline(row, output):
    times = np.asarray(row["logical_ms"]) / 1000
    actual, predicted = np.asarray(row["actual"]), np.asarray(row["predicted"])
    fig, axes = plt.subplots(6, 1, figsize=(12, 12), sharex=True, layout="constrained")
    fig.suptitle(f"Walidacja syntetyczna | {row['case']} | {row['profile']}\n{row['run_id']}", fontsize=12)
    axes[0].step(times, row["pending_commands"], where="post", label="Oczekujace polecenia")
    for event in row["commands"]:
        t = event["logical_ms"] / 1000
        if times[0] <= t <= times[-1]:
            sent = event["kind"] == "command_sent"
            axes[0].axvline(t, color="#3264b4" if sent else "#579b55", ls="--", alpha=.65)
            if sent:
                axes[0].annotate(f"{event['message']['value']:g} deg", (t, .97),
                                 xycoords=("data", "axes fraction"), fontsize=8, va="top")
    axes[0].set_ylabel("Polecenia")
    axes[0].set_title("Linie: wyslanie (niebieskie), odpowiedz (zielone). Cel prognozy: +50 ms.", fontsize=9)
    for i, name in enumerate(("Zamkniecie", "Otwarcie", "Prad [A]")):
        ax = axes[i + 1]
        ax.step(times, actual[:, i], where="post", label="Pomiar", color="#225ea8")
        ax.plot(times, predicted[:, i], label="Prognoza GRU", color="#d95f0e", lw=1.3)
        ax.set_ylabel(name)
        if i < 2:
            ax.set_ylim(-.08, 1.08)
    for i, name in enumerate(("Zamkniecie", "Otwarcie", "Prad")):
        axes[4].plot(times, np.asarray(row["scaled_residuals"])[:, i], label=name, lw=1)
    axes[4].plot(times, row["scores"], color="black", lw=1, ls=":", label="Maksimum")
    axes[4].axhline(row["threshold"], color="#c22", ls="--", label="Zamrozony prog")
    axes[4].set_ylabel("Blad / RMS")
    axes[5].step(times, row["labels"], where="post", label="Etykieta oceny", color="#888")
    axes[5].step(times, row["alarms"], where="post", label="Alarm (3 probki)", color="#c22")
    axes[5].set_ylim(-.08, 1.08)
    axes[5].set_yticks([0, 1])
    axes[5].set_ylabel("Zdarzenie / alarm")
    axes[5].set_xlabel("Czas logiczny [s]; prognoza i blad w chwili otrzymania pomiaru")
    for ax in axes:
        for a, b in intervals(row["labels"]):
            ax.axvspan(times[a], min(times[b - 1] + .05, times[-1]), color="#999", alpha=.1)
        ax.grid(alpha=.2)
        ax.legend(loc="upper right", fontsize=8, ncol=2)
    axes[-1].set_xlim(times[0], times[-1])
    fig.savefig(output, dpi=140)
    plt.close(fig)


def render(root, output):
    root, output = Path(root), Path(output)
    manifest = json.loads((root / "manifest.json").read_text())
    raw = (root / "report.json").read_bytes()
    if (manifest["status"] != "completed" or manifest["partition"] != "validation"
            or hashlib.sha256(raw).hexdigest() != manifest["report_sha256"]):
        raise ValueError("Expected a completed, unchanged validation diagnostic report.")
    report = json.loads(raw)
    selected = [s for s in report["sessions"] if s["case"] == "command_delay"]
    normal = [s for s in report["sessions"] if s["case"] == "normal"]
    # Include the normal session that most constrained the frozen threshold.
    selected += [max(normal, key=lambda s: s["peak_score"])] if normal else []
    output.mkdir(parents=True, exist_ok=False)
    lines = ["# Wykresy walidacji", "", "Wszystkie sesje opoznienia i normalna sesja o najwyzszym wyniku.",
             "Szare tlo: etykieta oceny, niedostepna detektorowi. Dane syntetyczne.", ""]
    for session in selected:
        name = session["run_id"]
        row = json.loads((root / "timelines" / (name + ".json")).read_text())
        plot_timeline(row, output / (name + ".png"))
        lines.append(f"- [{session['case']} / {session['profile']} / {name}]({name}.png)")
    (output / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostics", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"Rendered {render(args.diagnostics, args.output)} validation timelines.")


if __name__ == "__main__":
    main()
