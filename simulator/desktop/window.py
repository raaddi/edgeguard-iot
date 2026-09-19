"""Desktop laboratory adapter: shared simulation, linked navigation and experiments."""

import json
from pathlib import Path
from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot, QSaveFile, QIODevice
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QStackedWidget, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)
from simulator.__main__ import code_version
from simulator.house import HouseSimulation, SCENARIOS
from simulator.desktop.archive import measurements_csv, read_archive, restore_archive
from simulator.desktop.canvas import SignalGrid, SignalPlot
from simulator.desktop.house_canvas import HouseCanvas, COLORS
from simulator.desktop.panels import RunDialog, table, fill_table

RULES = {"gas_threshold": "Przekroczony próg", "actuator_mismatch": "Rozbieżność aktuatora", "simulated_link_loss": "Brak łączności w modelu"}


class ReplayWorker(QThread):
    result = Signal(object, str)

    def __init__(self, source, from_file=False, parent=None):
        super().__init__(parent)
        self.source, self.from_file = source, from_file

    def run(self):
        try:
            data = read_archive(self.source) if self.from_file else self.source
            sim = restore_archive(data)
            self.result.emit(sim, "")
        except Exception as error:
            self.result.emit(None, str(error))


class LaboratoryWindow(QMainWindow):
    def __init__(self, sim=None):
        super().__init__()
        self.sim = sim if sim is not None else HouseSimulation(run_id="desktop-lab")
        self.version, self.dirty, self.current = code_version(), False, "gas_01"
        self.worker = None
        self.previous_alerts = set()
        self.setWindowTitle("EdgeGuard | SmartHome Laboratory")
        self.resize(1440, 940)
        self.setMinimumSize(1080, 740)
        self.setStyleSheet(Path(__file__).with_name("theme.qss").read_text(encoding="utf-8"))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        self.build_workspace()
        self.build_menu()
        self.populate()
        self.refresh()

    def build_workspace(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 10, 14, 6)
        header = QHBoxLayout()
        brand = QLabel("EDGEGUARD  /  SmartHome Laboratory")
        brand.setObjectName("brand")
        header.addWidget(brand)
        header.addStretch()
        mode = QLabel("TRYB LOKALNY  •  WĘZŁY SYMULOWANE")
        mode.setStyleSheet("color: #5cedab; font: 10pt 'Consolas'")
        header.addWidget(mode)
        root.addLayout(header)
        toolbar = QHBoxLayout()
        self.play, self.single_step, self.save = QPushButton("Start"), QPushButton("Krok +1 s"), QPushButton("Zapisz JSON…")
        self.play.setObjectName("primary")
        self.play.setShortcut("F5")
        self.play.setToolTip("Start / Pauza (F5)")
        self.single_step.setShortcut("F6")
        self.single_step.setToolTip("Krok +1 s (F6)")
        self.play.clicked.connect(self.toggle)
        self.single_step.clicked.connect(self.step)
        self.save.clicked.connect(self.save_dialog)
        self.speed = QComboBox()
        for label, interval in [("0,5×", 2000), ("1×", 1000), ("2×", 500), ("5×", 200)]:
            self.speed.addItem(label, interval)
        self.speed.setCurrentIndex(1)
        self.speed.setAccessibleName("Tempo odtwarzania")
        self.speed.currentIndexChanged.connect(lambda: self.timer.setInterval(self.speed.currentData()))
        new_button = QPushButton("Nowy przebieg…")
        new_button.clicked.connect(self.new_dialog)
        for widget in (self.play, self.single_step, self.speed, new_button, self.save):
            toolbar.addWidget(widget)
        toolbar.addStretch()
        self.clock = QLabel()
        toolbar.addWidget(self.clock)
        root.addLayout(toolbar)
        self.summary = QLabel()
        self.summary.setObjectName("status")
        root.addWidget(self.summary)
        navigation = QWidget()
        nav = QVBoxLayout(navigation)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.addWidget(self.section("INSTALACJA"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Szukaj urządzenia / węzła…")
        self.search.textChanged.connect(self.filter_tree)
        nav.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(170)
        self.tree.currentItemChanged.connect(self.tree_selection)
        nav.addWidget(self.tree)
        nav.addWidget(QLabel("G czujnik  •  F wentylator\nL światło  •  S serwo"))
        map_panel = QWidget()
        map_layout = QVBoxLayout(map_panel)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_toolbar = QHBoxLayout()
        self.room_view = QComboBox()
        self.room_view.setAccessibleName("Widok makiety")
        self.room_view.currentIndexChanged.connect(self.change_view)
        map_toolbar.addWidget(self.room_view, 1)
        overview = QPushButton("Cały dom")
        overview.clicked.connect(lambda: self.room_view.setCurrentIndex(0))
        map_toolbar.addWidget(overview)
        map_layout.addLayout(map_toolbar)
        self.canvas = HouseCanvas(self.sim)
        self.canvas.selected.connect(self.select_device)
        self.canvas.room_selected.connect(self.focus_room)
        map_layout.addWidget(self.canvas, 1)
        caption = QLabel("Kliknij urządzenie → steruj po prawej. Dwuklik strefy → zbliżenie. Rzut orientacyjny; stan modelu także offline.")
        caption.setWordWrap(True)
        caption.setObjectName("muted")
        map_layout.addWidget(caption)
        inspector = QWidget()
        side = QVBoxLayout(inspector)
        side.setContentsMargins(8, 0, 8, 8)
        side.addWidget(self.section("URZĄDZENIE / STEROWANIE"))
        self.devices = QComboBox()
        self.devices.setAccessibleName("Wybrane urządzenie")
        self.devices.currentIndexChanged.connect(lambda: self.select_device(self.devices.currentData()))
        side.addWidget(self.devices)
        self.identity, self.reading, self.detail = QLabel(), QLabel(), QLabel()
        self.reading.setObjectName("reading")
        self.detail.setWordWrap(True)
        for widget in (self.identity, self.reading, self.detail):
            side.addWidget(widget)
        self.command_button, self.auto_button = QPushButton(), QPushButton("Przywróć AUTO")
        self.command_button.clicked.connect(self.command)
        self.auto_button.clicked.connect(lambda: self.perform(self.sim.auto_fan, self.current))
        side.addWidget(self.command_button)
        side.addWidget(self.auto_button)
        side.addWidget(self.section("TEST ZACHOWANIA"))
        self.scenario, self.targets = QComboBox(), QComboBox()
        self.scenario.setAccessibleName("Rodzaj zdarzenia")
        self.targets.setAccessibleName("Cel zdarzenia")
        for key, name in SCENARIOS.items():
            self.scenario.addItem(name, key)
        self.scenario.currentIndexChanged.connect(self.update_target)
        side.addWidget(self.scenario)
        side.addWidget(self.targets)
        self.duration = QSpinBox()
        self.duration.setRange(1, 120)
        self.duration.setValue(20)
        self.duration.setSuffix(" s")
        form = QFormLayout()
        form.addRow("Czas zdarzenia", self.duration)
        side.addLayout(form)
        self.inject_button = QPushButton("Dodaj zdarzenie")
        self.inject_button.clicked.connect(self.inject)
        side.addWidget(self.inject_button)
        hint = QLabel("Zdarzenie rusza od następnego kroku.\nGaz + awaria powiązanego wentylatora pozwolą porównać stan zadany i rzeczywisty stan modelu.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        side.addWidget(hint)
        self.findings = QLabel()
        self.findings.setWordWrap(True)
        side.addWidget(self.findings)
        side.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inspector)
        scroll.setMinimumWidth(295)
        top = QSplitter(Qt.Orientation.Horizontal)
        for widget in (navigation, map_panel, scroll):
            top.addWidget(widget)
        top.setSizes([240, 820, 340])
        top.setChildrenCollapsible(False)
        self.top_panel = top
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.refresh_data)
        chart = QWidget()
        chart_layout = QVBoxLayout(chart)
        chart_layout.setContentsMargins(4, 4, 4, 0)
        chart_toolbar = QHBoxLayout()
        self.chart_mode = QComboBox()
        self.chart_mode.setAccessibleName("Układ wykresów")
        self.chart_mode.addItems(["Cała makieta", "Pojedynczy kanał"])
        chart_toolbar.addWidget(self.chart_mode)
        self.chart_group = QComboBox()
        self.chart_group.setAccessibleName("Grupa wykresów")
        chart_toolbar.addWidget(self.chart_group)
        self.channels = QComboBox()
        self.channels.setAccessibleName("Kanał wykresu")
        self.channels.currentIndexChanged.connect(self.channel_changed)
        chart_toolbar.addWidget(self.channels, 1)
        self.expand_charts = QPushButton("Powiększ wykresy")
        self.expand_charts.setCheckable(True)
        self.expand_charts.toggled.connect(self.expand_chart_area)
        chart_toolbar.addWidget(self.expand_charts)
        self.chart_note = QLabel("Wspólny czas · gaz 0–1 / stany ON–OFF / serwa ° · przewiń po kolejne grupy")
        self.chart_note.setObjectName("muted")
        chart_layout.addLayout(chart_toolbar)
        chart_layout.addWidget(self.chart_note)
        legend = QLabel("Gaz: przerywana = próg. Aktuatory: przerywana = zadane, ciągła = raport z symulacji.")
        legend.setObjectName("muted")
        chart_layout.addWidget(legend)
        self.plot = SignalPlot(self.sim)
        self.all_plots = SignalGrid(self.sim)
        self.chart_group.currentIndexChanged.connect(lambda: self.all_plots.set_kind(self.chart_group.currentData()))
        self.chart_stack = QStackedWidget()
        self.chart_stack.addWidget(self.all_plots)
        self.chart_stack.addWidget(self.plot)
        chart_layout.addWidget(self.chart_stack, 1)
        self.chart_mode.currentIndexChanged.connect(self.change_chart_mode)
        self.change_chart_mode()
        self.tabs.addTab(chart, "Wykresy")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(250)
        self.tabs.addTab(self.log, "Dziennik")
        self.scenarios_table = table(["Zdarzenie", "Cel", "Status", "Początek [s]", "Koniec [s]"])
        self.tabs.addTab(self.scenarios_table, "Scenariusze")
        self.rules_table = table(["Cel", "Wskazanie reguły", "Źródło"])
        self.tabs.addTab(self.rules_table, "Reguły")
        self.nodes_table = table(["Węzeł", "Łączność modelu", "Komponenty", "Ostatnia sekwencja"])
        self.tabs.addTab(self.nodes_table, "Węzły")
        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        self.tabs.addTab(self.raw, "Telemetria JSON")
        self.manifest = QPlainTextEdit()
        self.manifest.setReadOnly(True)
        self.tabs.addTab(self.manifest, "Eksperyment")
        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.addWidget(top)
        vertical.addWidget(self.tabs)
        vertical.setSizes([500, 315])
        vertical.setChildrenCollapsible(False)
        self.vertical_splitter = vertical
        root.addWidget(vertical, 1)

    @staticmethod
    def section(text):
        label = QLabel(text)
        label.setObjectName("section")
        return label

    def build_menu(self):
        file_menu = self.menuBar().addMenu("Eksperyment")
        for label, callback, shortcut in [("Nowy…", self.new_dialog, "Ctrl+N"), ("Otwórz i odtwórz JSON…", self.open_dialog, "Ctrl+O"),
            ("Zapisz JSON…", self.save_dialog, "Ctrl+S"), ("Eksportuj pomiary CSV…", self.csv_dialog, ""),
            ("Sprawdź odtwarzalność", self.verify_replay, ""), ("Reset tego przebiegu…", self.reset_dialog, "")]:
            action = QAction(label, self)
            action.triggered.connect(callback)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            file_menu.addAction(action)
        help_menu = self.menuBar().addMenu("Pomoc")
        action = help_menu.addAction("Jak pracować / zakres wersji")
        action.triggered.connect(lambda: QMessageBox.information(self, "Laboratorium — instrukcja",
            "1. Wybierz urządzenie w drzewie lub na makiecie.\n2. Wydaj polecenie lub dodaj zdarzenie.\n3. Wykonaj krok; porównaj wykres i reguły.\n4. Zapisz eksperyment przez Ctrl+S.\n\nWszystkie węzły i pomiary są symulowane. Gaz jest w skali 0–1, nie ppm. Wykres pokazuje wyemitowane wiadomości, makieta wewnętrzny stan modelu.\n\nOkno Qt działa lokalnie; osobne narzędzia MQTT/SQLite opisuje docs/step-05-mqtt.md. ML i fizyczna elektronika pozostają do realizacji. Reguły nie stanowią dowodu ataku. Bufor: 3000 wiadomości, limit: 1000 działań / 10 000 kroków.\n\nOtwieranie pliku odtwarza własny przebieg, nie dane sprzętowe. CSV zawiera pomiary, nie ocenę modeli ML."))

    def populate(self):
        self.tree.blockSignals(True)
        self.devices.blockSignals(True)
        self.channels.blockSignals(True)
        self.room_view.blockSignals(True)
        self.tree.clear()
        self.devices.clear()
        self.channels.clear()
        self.room_view.clear()
        self.room_view.addItem("Makieta / cały dom", None)
        self.tree_items = {}
        for room in self.canvas.rooms():
            self.room_view.addItem(room["name"], room["id"])
            parent = QTreeWidgetItem([room["name"]])
            parent.setData(0, Qt.ItemDataRole.UserRole, ("room", room["id"]))
            self.tree.addTopLevelItem(parent)
            for cid, c in self.sim.components.items():
                if c["room"] != room["id"]:
                    continue
                child = QTreeWidgetItem([cid])
                child.setData(0, Qt.ItemDataRole.UserRole, ("device", cid))
                child.setToolTip(0, f"{c['name']} / {c['node']}")
                parent.addChild(child)
                self.tree_items[cid] = child
                self.devices.addItem(f"{cid} · {c['name']}", cid)
                self.channels.addItem(f"{cid} · {c['name']}", cid)
        self.chart_group.blockSignals(True)
        selected_group = self.chart_group.currentData()
        self.chart_group.clear()
        self.chart_group.addItem(f"Wszystkie ({len(self.sim.components)})", None)
        for kind, title, color in SignalGrid.GROUPS:
            count = sum(c["kind"] == kind for c in self.sim.components.values())
            self.chart_group.addItem(f"{title} ({count})", kind)
        self.chart_group.setCurrentIndex(max(0, self.chart_group.findData(selected_group)))
        self.chart_group.blockSignals(False)
        self.all_plots.set_kind(self.chart_group.currentData())
        self.tree.expandAll()
        for widget in (self.tree, self.devices, self.channels, self.room_view):
            widget.blockSignals(False)
        self.canvas.room = None
        self.select_device(self.current if self.current in self.sim.components else "gas_01")
        self.channel_changed()
        self.filter_tree()

    def filter_tree(self):
        term = self.search.text().casefold()
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            visible = False
            for n in range(parent.childCount()):
                child = parent.child(n)
                match = term in (parent.text(0) + child.text(0) + child.toolTip(0)).casefold()
                child.setHidden(not match)
                visible |= match
            parent.setHidden(bool(term) and not visible)

    def tree_selection(self, item, previous):
        if item:
            kind, value = item.data(0, Qt.ItemDataRole.UserRole)
            self.select_device(value) if kind == "device" else self.focus_room(value)

    def focus_room(self, room):
        self.room_view.setCurrentIndex(self.room_view.findData(room))

    def change_view(self):
        self.canvas.room = self.room_view.currentData()
        self.canvas.update()

    def select_device(self, cid):
        if cid not in self.sim.components:
            return
        self.current = self.canvas.current = cid
        self.devices.blockSignals(True)
        self.devices.setCurrentIndex(self.devices.findData(cid))
        self.devices.blockSignals(False)
        self.tree.blockSignals(True)
        self.tree.setCurrentItem(self.tree_items[cid])
        self.tree.blockSignals(False)
        component = self.sim.components[cid]
        if self.canvas.room is not None:
            self.focus_room(component["room"])
        self.channels.setCurrentIndex(self.channels.findData(cid))
        self.update_target()
        self.refresh()

    def channel_changed(self):
        if self.channels.currentData():
            self.plot.component = self.channels.currentData()
            self.plot.color = COLORS[self.sim.components[self.plot.component]["kind"]]
            self.plot.setAccessibleName(f"Telemetria {self.plot.component}; przerwy oznaczają brak danych")
            self.plot.update()

    def change_chart_mode(self):
        single = self.chart_mode.currentIndex() == 1
        self.chart_stack.setCurrentIndex(int(single))
        self.channels.setVisible(single)
        self.chart_group.setVisible(not single)
        self.chart_note.setVisible(not single)

    def expand_chart_area(self, expanded):
        if expanded:
            self.previous_panel_sizes = self.vertical_splitter.sizes()
        self.top_panel.setVisible(not expanded)
        self.expand_charts.setText("Przywróć makietę" if expanded else "Powiększ wykresy")
        if not expanded:
            self.vertical_splitter.setSizes(self.previous_panel_sizes)

    def update_target(self):
        kind = self.scenario.currentData()
        options = list(self.sim.nodes) if kind == "node_offline" else [cid for cid, c in self.sim.components.items() if c["kind"] == ("fan" if kind == "fan_failure" else "gas")]
        item = self.sim.components[self.current]
        preferred = item["node"] if kind == "node_offline" else self.current if self.current in options else next((cid for cid in options if self.sim.components[cid]["room"] == item["room"]), options[0])
        self.targets.clear()
        for cid in options:
            self.targets.addItem(cid, cid)
        self.targets.setCurrentIndex(self.targets.findData(preferred))

    def scenario_target(self):
        return self.targets.currentData()

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
            self.log.appendPlainText(f"krok {self.sim.time:05d} | {'ODRZUCONO: offline' if result is False else 'ZAPISANO'} | " + " / ".join(map(str, args)))
        except (ValueError, KeyError) as error:
            self.pause()
            self.log.appendPlainText(f"BŁĄD | {error}")
        self.refresh()

    def step(self):
        try:
            self.sim.step()
            self.dirty = True
        except ValueError as error:
            self.pause()
            self.log.appendPlainText(f"LIMIT | {error}")
        current = {(a['target'], a['rule']) for a in self.sim.alerts}
        for target, rule in sorted(current - self.previous_alerts):
            self.log.appendPlainText(f"t={self.sim.time - 1:05d} | REGUŁA | {target}: {RULES[rule]}")
        for target, rule in sorted(self.previous_alerts - current):
            self.log.appendPlainText(f"t={self.sim.time - 1:05d} | USTAŁO | {target}: {RULES[rule]}")
        self.previous_alerts = current
        self.refresh()

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
        if not hasattr(self, 'tree_items'):
            return
        running = self.timer.isActive()
        self.play.setText("Pauza" if running else "Start całej makiety")
        self.single_step.setEnabled(not running)
        self.clock.setText(f"{'PRACA' if running else 'PAUZA'}  |  t = {self.sim.time - 1:05d} s")
        online_count = sum(self.sim.nodes.values())
        self.summary.setText(f"{self.sim.run_id}   /   SEED {self.sim.seed}     |     ONLINE {online_count}/{len(self.sim.nodes)}     |     REGUŁY {len(self.sim.alerts)}     |     WIADOMOŚCI {self.sim.message_count}")
        item = self.sim.components[self.current]
        online = self.sim.nodes[item["node"]]
        self.identity.setText(f"{self.current} · {item['node']}\n{'ONLINE / model' if online else 'OFFLINE / brak nowych wiadomości'}")
        self.identity.setStyleSheet(f"color: {'#8795a7' if online else '#ff657a'}")
        gas = item["kind"] == "gas"
        self.command_button.setVisible(not gas)
        self.auto_button.setVisible(item["kind"] == "fan")
        if gas:
            self.reading.setText(f"{self.sim.sensors[self.current]['value']:.3f}")
            self.detail.setText(f"Stan modelu / skala 0–1, nie ppm.\nPróg reguły: {self.sim.profile['threshold']:.3f}.\nWykres: wyemitowane wiadomości.")
        else:
            state = self.sim.actuators[self.current]
            servo = item["kind"] == "servo"
            self.reading.setText(f"{state['simulated']}°" if servo else "ON" if state["simulated"] else "OFF")
            self.detail.setText(f"Tryb {state['mode'].upper()} · zadane {state['commanded']} → model {state['simulated']}\nTelemetria i reguły od następnego kroku.")
            self.command_button.setText(("Zamknij" if state["commanded"] else "Otwórz") if servo else ("Wyłącz" if state["commanded"] else "Włącz"))
        active = sum(s["start"] <= self.sim.time - 1 < s["end"] for s in self.sim.scenarios)
        pending = sum(s["start"] > self.sim.time - 1 for s in self.sim.scenarios)
        self.findings.setText(f"Scenariusze: {active} aktywne / {pending} oczekujące\nWskazania reguł: {len(self.sim.alerts)} — szczegóły na dole.")
        for cid, tree_item in self.tree_items.items():
            c = self.sim.components[cid]
            value = f"{self.sim.sensors[cid]['value']:.3f}" if c['kind'] == 'gas' else str(self.sim.actuators[cid]['simulated'])
            tree_item.setText(0, f"{cid}  ·  {value}")
            tree_item.setForeground(0, QColor(COLORS[c['kind']] if self.sim.nodes[c['node']] else '#ff657a'))
        self.statusBar().showMessage(f"Bufor {len(self.sim.history)}/3000 · pominięte offline {self.sim.suppressed_messages} · usunięte z bufora {self.sim.evicted_messages}    |    Reguły ≠ ML · Qt: symulacja lokalna, bez połączenia z kolektorem")
        self.canvas.update()
        self.plot.update()
        self.all_plots.refresh()
        self.refresh_data()

    def refresh_data(self):
        if not hasattr(self, 'manifest'):
            return
        index = self.tabs.currentIndex()
        if index == 2:
            fill_table(self.scenarios_table, [(SCENARIOS[s['kind']], s['target'], 'oczekuje' if self.sim.time-1 < s['start'] else 'aktywne' if self.sim.time-1 < s['end'] else 'zakończone', s['start'], s['end']) for s in self.sim.scenarios])
        elif index == 3:
            fill_table(self.rules_table, [(a['target'], RULES[a['rule']], 'model / prosta reguła') for a in self.sim.alerts])
        elif index == 4:
            latest = {m['device_id']: m['sequence_number'] for m in self.sim.history}
            fill_table(self.nodes_table, [(node, 'online' if online else 'offline', sum(c['node'] == node for c in self.sim.components.values()), latest.get(node, 'brak w buforze')) for node, online in self.sim.nodes.items()])
        elif index == 5:
            node = self.sim.components[self.current]['node']
            message = next((m for m in reversed(self.sim.history) if m['device_id'] == node), None)
            self.raw.setPlainText(f"{node} / {'ostatnia wiadomość' if self.sim.nodes[node] else 'OFFLINE — ostatnia wiadomość, nie stan bieżący'}\n" + (json.dumps(message, ensure_ascii=False, indent=2) if message else 'Brak wiadomości w buforze.'))
        elif index == 6:
            self.manifest.setPlainText("Eksperyment → Zapisz JSON / Eksportuj CSV / Otwórz / Sprawdź odtwarzalność\nEtykiety scenariuszy nie są wejściem modelu ML.\n\n" + json.dumps(self.sim.export(self.version)['manifest'], ensure_ascii=False, indent=2))

    def replace_simulation(self, sim, dirty=False):
        self.timer.stop()
        self.sim = self.canvas.sim = self.plot.sim = sim
        self.all_plots.set_simulation(sim)
        self.version, self.dirty = code_version(), dirty
        self.previous_alerts = {(a['target'], a['rule']) for a in sim.alerts}
        self.log.clear()
        self.log.appendPlainText(f"SESJA | {sim.run_id} | seed={sim.seed} | t={sim.time-1}")
        for action in sim.actions[-200:]:
            description = SCENARIOS[action['kind']] if action['type'] == 'scenario' else action['type']
            result = "odrzucono" if action.get('accepted') is False else str(action.get('value', ''))
            self.log.appendPlainText(f"krok {action['at_step']:05d} | ARCHIWUM | {description} / {action['target']} / {result}")
        self.populate()
        self.refresh()

    def confirm_replace(self):
        self.pause()
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "Niezapisany przebieg", "Zapisać bieżący przebieg przed kontynuacją?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Discard or (answer == QMessageBox.StandardButton.Save and self.save_dialog())

    def new_dialog(self):
        self.pause()
        dialog = RunDialog(self.sim, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and self.confirm_replace():
            self.replace_simulation(HouseSimulation(dialog.seed.value(), dialog.nodes.value(), dialog.extra.value(), dialog.run_id.text()))

    def reset_dialog(self):
        if self.confirm_replace():
            sim = self.sim
            self.replace_simulation(HouseSimulation(sim.seed, sim.node_count, sim.extra_nodes, sim.run_id, sim.profile))

    def save_to(self, path):
        self.pause()
        data = json.dumps(self.sim.export(self.version), ensure_ascii=False, indent=2).encode("utf-8")
        output = QSaveFile(str(path))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(output.errorString())
        if output.write(data) != len(data):
            output.cancelWriting()
            raise OSError(output.errorString())
        if not output.commit():
            raise OSError(output.errorString())
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
        self.log.appendPlainText(f"EKSPORT JSON | {path}")
        return True

    def csv_dialog(self):
        self.pause()
        path, _ = QFileDialog.getSaveFileName(self, "Eksport pomiarów z bufora", f"{self.sim.run_id}.csv", "Pomiary CSV (*.csv)")
        if path:
            try:
                measurements_csv(self.sim, path)
                self.log.appendPlainText(f"EKSPORT CSV | {path} | Pełny eksperyment zapisz osobno jako JSON.")
            except OSError as error:
                QMessageBox.warning(self, "Nie zapisano CSV", str(error))

    def open_dialog(self):
        self.pause()
        path, _ = QFileDialog.getOpenFileName(self, "Otwórz i odtwórz eksperyment", "", "Eksperyment JSON (*.json)")
        if path and self.confirm_replace():
            self.start_replay(path, from_file=True)

    def verify_replay(self):
        self.pause()
        self.start_replay(self.sim.export(self.version))

    def start_replay(self, source, from_file=False):
        if self.worker is not None:
            return
        self.pause()
        self.centralWidget().setEnabled(False)
        self.menuBar().setEnabled(False)
        self.statusBar().showMessage("Odtwarzanie eksperymentu… bieżąca sesja pozostaje zachowana do zakończenia weryfikacji.")
        self.worker = ReplayWorker(source, from_file, self)
        self.worker.result.connect(self.replay_result)
        self.worker.finished.connect(self.replay_finished)
        self.worker.start()

    @Slot(object, str)
    def replay_result(self, sim, error):
        if error:
            QMessageBox.warning(self, "Nie odtworzono eksperymentu", error)
        elif self.worker.from_file:
            self.replace_simulation(sim)
            self.log.appendPlainText("IMPORT | Odtworzono stan i telemetrię. Dalsza praca jest zapisywana z bieżącą wersją kodu.")
        else:
            self.log.appendPlainText("WERYFIKACJA | Identyczny stan, telemetria i działania.")
            self.tabs.setCurrentIndex(1)

    @Slot()
    def replay_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.centralWidget().setEnabled(True)
        self.menuBar().setEnabled(True)
        self.refresh()

    def closeEvent(self, event):
        if self.worker is not None:
            event.ignore()
            return
        if self.confirm_replace():
            event.accept()
        else:
            event.ignore()
