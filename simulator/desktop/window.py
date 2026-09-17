"""Small desktop proof of interaction; the simulation owns all domain state."""

import json
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton, QSpinBox, QSplitter, QTextEdit, QVBoxLayout, QWidget)
from simulator.__main__ import code_version
from simulator.house import HouseSimulation, SCENARIOS
from simulator.desktop.canvas import GarageCanvas, SignalPlot

STYLE = """
QWidget { background: #202832; color: #dce3ec; font: 10pt 'Segoe UI'; }
QLabel { background: transparent; }
QLabel#title { font-size: 15pt; font-weight: 600; }
QLabel#reading { font: 24pt 'Consolas'; color: #75b8fa; }
QLabel#muted { color: #a4b1c0; }
QPushButton, QComboBox, QSpinBox { background: #2c3845; border: 1px solid #526272; border-radius: 3px; padding: 6px; }
QPushButton:hover { background: #3c4c5d; border-color: #75b8fa; }
QPushButton:focus, QComboBox:focus, QSpinBox:focus { border: 2px solid #75b8fa; }
QPushButton:disabled { color: #788795; border-color: #394654; }
QPushButton#primary { background: #365d80; border-color: #75b8fa; }
QTextEdit { background: #171d24; border: 1px solid #394654; padding: 5px; font: 9pt 'Consolas'; }
QSplitter::handle { background: #394654; }
QStatusBar { background: #171d24; }
"""


class GarageWindow(QMainWindow):
    def __init__(self, sim=None):
        super().__init__()
        self.sim = sim if sim is not None else HouseSimulation(run_id="qt-garage")
        self.version = code_version()
        self.dirty = False
        self.current = "gas_01"
        self.setWindowTitle("EdgeGuard — laboratorium garażu / prototyp Qt")
        self.resize(1240, 820)
        self.setMinimumSize(900, 650)
        self.setStyleSheet(STYLE)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 12, 16, 8)
        title = QLabel("EdgeGuard   /   Laboratorium garażu")
        title.setObjectName("title")
        layout.addWidget(title)
        note = QLabel("Prototyp desktopowy · dane syntetyczne · kliknij urządzenie na schemacie")
        note.setObjectName("muted")
        layout.addWidget(note)
        toolbar = QHBoxLayout()
        self.play = QPushButton("Start")
        self.play.setObjectName("primary")
        self.play.clicked.connect(self.toggle)
        self.single_step = QPushButton("Krok +1 s")
        self.single_step.clicked.connect(self.step)
        self.speed = QComboBox()
        for label, interval in [("0,5×", 2000), ("1×", 1000), ("2×", 500), ("5×", 200)]:
            self.speed.addItem(label, interval)
        self.speed.setCurrentIndex(1)
        self.speed.setAccessibleName("Tempo odtwarzania")
        self.speed.currentIndexChanged.connect(self.change_speed)
        self.save = QPushButton("Zapisz przebieg…")
        self.save.clicked.connect(self.save_dialog)
        for widget in (self.play, self.single_step, self.speed, self.save):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        self.clock = QLabel()
        toolbar.addWidget(self.clock)
        layout.addLayout(toolbar)
        self.canvas = GarageCanvas(self.sim)
        self.canvas.selected.connect(self.select_device)
        self.plot = SignalPlot(self.sim)
        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.addWidget(self.canvas)
        vertical.addWidget(self.plot)
        vertical.setSizes([460, 200])
        vertical.setChildrenCollapsible(False)
        panel = QWidget()
        panel.setMinimumWidth(300)
        side = QVBoxLayout(panel)
        side.setContentsMargins(12, 0, 0, 0)
        side.addWidget(QLabel("WYBRANE URZĄDZENIE"))
        self.devices = QComboBox()
        self.devices.setAccessibleName("Wybrane urządzenie")
        for cid in self.canvas.AREAS:
            self.devices.addItem(self.sim.components[cid]["name"], cid)
        self.devices.currentIndexChanged.connect(lambda _: self.select_device(self.devices.currentData()))
        side.addWidget(self.devices)
        self.identity, self.reading, self.detail = QLabel(), QLabel(), QLabel()
        self.reading.setObjectName("reading")
        self.detail.setWordWrap(True)
        for widget in (self.identity, self.reading, self.detail):
            side.addWidget(widget)
        self.command_button = QPushButton()
        self.command_button.clicked.connect(self.command)
        self.auto_button = QPushButton("Przywróć automatykę wentylatora")
        self.auto_button.clicked.connect(lambda: self.perform(self.sim.auto_fan, self.current))
        side.addWidget(self.command_button)
        side.addWidget(self.auto_button)
        side.addSpacing(12)
        side.addWidget(QLabel("KONTROLOWANE ZDARZENIE"))
        self.scenario = QComboBox()
        self.scenario.setAccessibleName("Rodzaj zdarzenia")
        for key, name in SCENARIOS.items():
            self.scenario.addItem(name, key)
        self.scenario.currentIndexChanged.connect(self.update_target)
        side.addWidget(self.scenario)
        self.target = QLabel()
        side.addWidget(self.target)
        self.duration = QSpinBox()
        self.duration.setRange(1, 120)
        self.duration.setValue(20)
        self.duration.setSuffix(" s")
        form = QFormLayout()
        form.addRow("Czas zdarzenia", self.duration)
        side.addLayout(form)
        self.inject_button = QPushButton("Dodaj zdarzenie od następnego kroku")
        self.inject_button.clicked.connect(self.inject)
        side.addWidget(self.inject_button)
        self.findings = QLabel()
        self.findings.setWordWrap(True)
        side.addWidget(self.findings)
        side.addWidget(QLabel("DZIENNIK DZIAŁAŃ"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(200)
        self.log.setMinimumHeight(90)
        side.addWidget(self.log, 1)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(vertical)
        splitter.addWidget(panel)
        splitter.setSizes([830, 350])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        self.refresh()
        self.update_target()

    def select_device(self, cid):
        self.current = self.canvas.current = cid
        self.devices.blockSignals(True)
        self.devices.setCurrentIndex(self.devices.findData(cid))
        self.devices.blockSignals(False)
        self.refresh()

    def scenario_target(self):
        kind = self.scenario.currentData()
        return self.sim.components["gas_01"]["node"] if kind == "node_offline" else "fan_01" if kind == "fan_failure" else "gas_01"

    def update_target(self):
        self.target.setText(f"Cel w garażu: {self.scenario_target()}")

    def inject(self):
        self.perform(self.sim.inject, self.scenario.currentData(), self.scenario_target(), self.duration.value())

    def command(self):
        state, item = self.sim.actuators[self.current], self.sim.components[self.current]
        value = 0 if state["commanded"] else 110 if item["kind"] == "servo" else 1
        self.perform(self.sim.command, self.current, value)

    def perform(self, function, *args):
        try:
            result = function(*args)
            self.dirty = True
            self.log.append(f"krok {self.sim.time:05d} | {'ODRZUCONO: offline' if result is False else 'ZAPISANO'} | " + " / ".join(map(str, args)))
        except (ValueError, KeyError) as error:
            self.pause()
            self.log.append(f"BŁĄD | {error}")
        self.refresh()

    def step(self):
        try:
            self.sim.step()
            self.dirty = True
        except ValueError as error:
            self.pause()
            self.log.append(f"LIMIT | {error}")
        self.refresh()

    def change_speed(self):
        self.timer.setInterval(self.speed.currentData())

    def toggle(self):
        if self.timer.isActive():
            self.pause()
        else:
            self.timer.start(self.speed.currentData())
        self.refresh()

    def pause(self):
        self.timer.stop()
        self.refresh()

    def refresh(self):
        running = self.timer.isActive()
        self.play.setText("Pauza" if running else "Start")
        self.single_step.setEnabled(not running)
        self.clock.setText(f"{'PRACA' if running else 'PAUZA'}   |   t = {self.sim.time - 1:05d} s")
        item = self.sim.components[self.current]
        online = self.sim.nodes[item["node"]]
        self.identity.setText(f"{self.current} · {item['node']}\n{'ONLINE (model)' if online else 'OFFLINE (model)'}")
        gas = item["kind"] == "gas"
        self.command_button.setVisible(not gas)
        self.auto_button.setVisible(item["kind"] == "fan")
        if gas:
            self.reading.setText(f"{self.sim.sensors[self.current]['value']:.3f}")
            self.detail.setText("Stan modelu / skala 0–1, nie ppm.\nPróg automatyki: 0,323. Wykres poniżej pokazuje wyłącznie wyemitowane wiadomości.")
        else:
            state = self.sim.actuators[self.current]
            servo = item["kind"] == "servo"
            self.reading.setText(f"{state['simulated']}°" if servo else "ON" if state["simulated"] else "OFF")
            self.detail.setText(f"Tryb: {state['mode'].upper()}\nZadane: {state['commanded']} → model: {state['simulated']}\nTelemetria i reguły aktualizują się przy kroku.")
            self.command_button.setText(("Zamknij" if state["commanded"] else "Otwórz") if servo else ("Wyłącz" if state["commanded"] else "Włącz"))
        labels = {"gas_threshold": "przekroczony próg", "actuator_mismatch": "rozbieżność aktuatora", "simulated_link_loss": "brak łączności"}
        findings = [f"{a['target']}: {labels[a['rule']]}" for a in self.sim.alerts]
        active = sum(s["start"] <= self.sim.time - 1 < s["end"] for s in self.sim.scenarios)
        pending = sum(s["start"] > self.sim.time - 1 for s in self.sim.scenarios)
        self.findings.setText(f"Zdarzenia: {active} aktywne / {pending} oczekujące\nReguły: " + ("; ".join(findings) if findings else "brak wskazań"))
        self.statusBar().showMessage(f"Model całego domu: {len(self.sim.nodes)} węzłów | Widok: garaż | Bufor: {len(self.sim.history)} | Pominięte offline: {self.sim.suppressed_messages} | MQTT / ML: jeszcze niewdrożone")
        self.canvas.update()
        self.plot.update()

    def save_to(self, path):
        # Pause before snapshotting so manifest, telemetry and actions agree.
        self.pause()
        Path(path).write_text(json.dumps(self.sim.export(self.version), ensure_ascii=False, indent=2), encoding="utf-8")
        self.dirty = False

    def save_dialog(self):
        self.pause()
        path, _ = QFileDialog.getSaveFileName(self, "Zapisz eksperyment", f"{self.sim.run_id}.json", "Eksperyment JSON (*.json)")
        if not path:
            return False
        try:
            self.save_to(path)
        except OSError as error:
            QMessageBox.warning(self, "Nie zapisano danych", str(error))
            return False
        self.log.append(f"EKSPORT | {path}")
        return True

    def closeEvent(self, event):
        self.pause()
        if self.dirty:
            answer = QMessageBox.question(self, "Niezapisany przebieg", "Zapisać przebieg przed zamknięciem?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel or (answer == QMessageBox.StandardButton.Save and not self.save_dialog()):
                event.ignore()
                return
        event.accept()
