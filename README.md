# EdgeGuard IoT

Master's thesis project: anomaly detection in a distributed Smart Home IoT
environment, with inference planned on a Raspberry Pi gateway.

## Status

The current branch includes a [SmartHome laboratory](docs/smarthome-laboratory.md)
based on the supplied engineering-project material: an approximate interactive floor
plan, device controls, four bounded scenarios, multiple simulated nodes, telemetry,
and JSON/CSV experiment exports. All nodes remain simulated. A separate
[local MQTT/SQLite exercise](docs/step-05-mqtt.md) now sends headless house telemetry
through Mosquitto to a validating collector. A [read-only HTTP API](docs/step-06-api.md)
now exposes stored devices and telemetry. The [Qt collector view](docs/step-07-collector-view.md)
reads this history over HTTP. MQTT control integration and ML remain pending.
The reference-code profile has 10 LEDs, 6 servos, 4 gas
sensors and 4 fans; physical counts and detailed placement still need confirmation.

The repository contains the agreed specification, a modular Polish LaTeX thesis,
local PDF build scripts, an Overleaf exporter, a CSV-to-LaTeX results exporter,
tests and a thesis GitHub Actions workflow.

The original single-node CLI exercise remains available for learning the generator.
Both simulator entry points now emit validated telemetry **1.0** using the shared
[contract and Polish exercise](docs/step-03-telemetry-contract.md).
The remaining API endpoints, ESP32 firmware and ML detectors remain to be implemented
according to [PROJECT_SPEC.md](PROJECT_SPEC.md).
The [ML research and instrumentation plan (Polish)](docs/ml-research-plan.md)
records the core temporal-model study, proposed physical feedback, evaluation
protocol and the interactive UI requirements. These are planned capabilities.
The system must support 1-3 physical ESP32 boards plus configurable simulated
nodes without a fixed architectural node limit.

## First simulation exercise

**Desktop laboratory:** [Python + Qt walkthrough](docs/desktop-laboratory.md).
The native workspace now covers the whole house, device navigation and controls,
fault scenarios, telemetry, JSON/CSV exports and verified experiment replay.
It uses the same simulation model and has a black console theme. Connecting this
window's controls to MQTT, ML and physical validation remains pending. Select
**Kolektor — dane z API** in the desktop workspace to read persisted telemetry.
With the existing virtual environment:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe -m simulator.desktop
~~~

**Interactive application:** [SmartHome laboratory guide](docs/smarthome-laboratory.md).
With `.venv` already created, run from the repository root:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe -m streamlit run simulator_app.py
~~~

Install dependencies once; subsequent launches only need the second command.
This invokes Python directly without changing PowerShell's script execution policy.
Open http://127.0.0.1:8501 for the live chart,
start/pause, single stepping and a consolidated diagnostic console: model, signals,
actuator controls and scenario tests together. Configuration, inventory and experiment
exports (including reset) are expandable panels. See the Polish guide for a short walkthrough.
The earlier single-node exercise is preserved in `simulator/lesson_app.py`.
Qt is the actively developed laboratory interface; Streamlit is retained as the
earlier comparison interface. The simulation engine remains independent of both.
The gateway dashboard deployment will be evaluated separately.

Follow the [step-by-step Polish guide](docs/step-01-simulator.md).
From the repository root on Windows, with Python 3.14 installed:

~~~powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-ui.txt
.\.venv\Scripts\python.exe -m simulator --seed 42 --samples 5
.\.venv\Scripts\python.exe -m pytest -q
~~~

Skip environment creation if `.venv` already exists. The generator needs no
network or hardware after dependencies are installed. Telemetry validation uses
`jsonschema`; the signal generator itself uses the standard library. Its normalized signal is not a
calibrated MQ-9 measurement. Logical timestamps advance by one second; output
is generated immediately. Metadata goes to stderr and telemetry to stdout.

## Check telemetry without hardware

After installing the dependencies above, run this from the repository root:

~~~powershell
.\.venv\Scripts\python.exe -m simulator --samples 3 --run-id contract-lesson | .\.venv\Scripts\python.exe -m contracts
~~~

Expected output: `Validated 3 telemetry messages (schema 1.0).`
The run manifest is printed separately on stderr; it is not an error and is not
passed into the validator. This checks the message format locally, without MQTT
or SQLite. It does not test network delivery or anomaly detection.

To check a saved JSONL file, use `python -m contracts path/to/telemetry.jsonl`
with the project's Python environment. Each line must contain one telemetry
message; the full laboratory experiment JSON export has a different structure.
See the [Polish contract lesson](docs/step-03-telemetry-contract.md) for field
meanings and the distinction between zero, unavailable readings and actuator feedback.

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
| simulator/ | Offline signal generator and interactive SmartHome model |
| contracts/ | Shared telemetry schema, strict decoder and examples |
| scripts/ | Build tools, Overleaf export and CSV table export |
| experiments/ | Metadata/CSV templates and ignored local run files |
| data/ | Ignored raw and processed datasets |
| ml/models/ | Reserved local model artifacts |
| edge/ | Local MQTT collector and validated SQLite telemetry storage |
| mqtt/ | Loopback Mosquitto configuration |
| tests/ | Simulator, real MQTT/SQLite and results-export verification |
| docs/ | Writing plan and project workflow |
| .github/workflows/ | Python tests, thesis build and downloadable PDF |

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
