# EdgeGuard IoT

Master's thesis project: anomaly detection in a distributed Smart Home IoT
environment, with inference planned on a Raspberry Pi gateway.

## Status

The repository contains the agreed specification, a modular Polish LaTeX thesis,
local PDF build scripts, an Overleaf exporter, a CSV-to-LaTeX results exporter,
tests and a thesis GitHub Actions workflow.

**The simulator, collector, API, ESP32 firmware and ML detectors are not
implemented yet.** Their scope remains defined in [PROJECT_SPEC.md](PROJECT_SPEC.md).
The system must support 1-3 physical ESP32 boards plus configurable simulated
nodes without a fixed architectural node limit.

## Start with Overleaf

[Instrukcja po polsku](thesis/README.md) |
[Plan rozdziałów](docs/thesis-outline.md) |
[Praca offline i Git](docs/workflow.md)

Generate a standalone ZIP from the repository root:

~~~powershell
.\scripts\export-overleaf.ps1
~~~

Upload output/EdgeGuard_Magisterka_Overleaf.zip to Overleaf.
Select main.tex and the XeLaTeX compiler.

## Work offline on a Windows laptop

Prepare once with Internet access:

~~~powershell
.\scripts\setup-latex.ps1
.\scripts\build-thesis.ps1
.\scripts\build-thesis.ps1 -Offline -Open
~~~

PDF: thesis/build/main.pdf. New LaTeX packages/fonts may need another online build.
No Python, Docker or electronics are needed to write and build the thesis.

## Repository

| Directory | Purpose |
|---|---|
| thesis/ | Chapters, bibliography, figures and optional result tables |
| scripts/ | Build tools, Overleaf export and CSV table export |
| experiments/ | Metadata/CSV templates and ignored local run files |
| data/ | Ignored raw and processed datasets |
| ml/models/ | Reserved local model artifacts |
| tests/ | Results-export verification |
| docs/ | Writing plan and project workflow |
| .github/workflows/ | Automatic thesis build and downloadable PDF |

## Planned architecture and stack

Simulator and ESP32 nodes -> MQTT -> collector/validation -> SQLite/FastAPI ->
later inference and alerts. Training takes place on the workstation.
The laptop can host the planned software-only prototype; real telemetry and
Raspberry Pi resource measurements remain later research requirements.

Planned technologies: Python, Mosquitto, paho-mqtt, SQLite, FastAPI, scikit-learn;
C++ with PlatformIO and Arduino Framework for ESP32.

## Roadmap

1. Writing scaffold and reproducible document builds.
2. Milestone 1: simulator, MQTT contracts, collector, database, API and tests.
3. Physical integration and early real telemetry collection.
4. Rules and 2-3 ML methods; reproducible evaluation.
5. Raspberry Pi measurements, results, discussion and thesis completion.

No license has been selected yet. External sources retain their own licenses.
