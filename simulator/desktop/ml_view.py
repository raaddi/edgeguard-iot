"""Qt view of real saved forecasts, detector scores and experiment evidence."""

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, Signal, Slot, QSignalBlocker
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSlider, QSplitter, QVBoxLayout, QWidget)

from simulator.desktop.ml_timeline import read_timeline
from simulator.desktop.panels import table, fill_table

CYAN, AMBER, RED, MUTED = "#5bd5ed", "#f2c879", "#ff798e", "#9aaabd"
METHOD_NAMES = {"gru": "GRU", "persistence": "Ostatni odczyt", "isolation_forest": "Isolation Forest",
                "temporal_rules": "Reguły czasowe"}
CASE_NAMES = {"normal": "Praca poprawna", "command_delay": "Opóźniona odpowiedź", "motion_stall": "Zablokowany ruch", "open_contact_stuck_low": "Nieaktywna krańcówka otwarcia"}
CONDITION_NAMES = {"cycles": "Spokojne cykle", "repeats": "Powtórzenia poleceń", "idle": "Bezczynność", "slow": "Wolniejszy poprawny ruch", "reversals": "Odwrócenia kierunku"}
POLICY_NAMES = {"sample_max": "Maksimum normalnych próbek", "sustained_max": "Utrzymujący się błąd"}
CHANNEL_NAMES = ("Krańcówka zamknięcia", "Krańcówka otwarcia", "Prąd napędu [A]")


class TimelineWorker(QThread):
    result = Signal(object, str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = Path(path)

    def run(self):
        try:
            self.result.emit(read_timeline(self.path), "")
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            self.result.emit(None, str(error))


class ResearchPlot(QWidget):
    selected = Signal(int)

    def __init__(self, scores=False, parent=None):
        super().__init__(parent)
        self.is_score = scores
        self.data, self.channel, self.method, self.cursor, self.truth = None, 1, "gru", 0, False
        self.setMinimumSize(400, 180)
        self.setAccessibleName("Wynik i próg detektora" if scores else "Pomiar i prognoza GRU")

    def series(self):
        if self.data is None:
            return []
        if self.is_score:
            return [(self.data["scores"][self.method], CYAN, False)]
        return [([r[self.channel] for r in self.data["actual"]], CYAN, self.channel < 2),
                ([r[self.channel] for r in self.data["predicted"]], AMBER, False)]

    def box(self):
        return QRectF(58, 58, self.width() - 82, self.height() - 92)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#0d141e"))
        p.setFont(QFont("Segoe UI", 10))
        p.setPen(QColor("#e8eff7"))
        title = f"Wynik · {METHOD_NAMES[self.method]}" if self.is_score else f"Pomiar i prognoza GRU · {CHANNEL_NAMES[self.channel]}"
        p.drawText(18, 24, title)
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor(CYAN))
        p.drawText(18, 43, "Wynik detektora" if self.is_score else "━ Pomiar")
        p.setPen(QColor(RED if self.is_score else AMBER))
        p.drawText(160, 43, "┄ Próg alarmu" if self.is_score else "━ Prognoza GRU · +50 ms")
        if self.data is None:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Otwórz zapisaną oś czasu, aby zobaczyć wyniki.")
            p.end()
            return
        box, times = self.box(), self.data["logical_ms"]
        first, last = times[0], times[-1]
        threshold = self.data["thresholds"][self.method] if self.is_score else None
        values = [v for series, _, _ in self.series() for v in series if v is not None]
        low = min(0, min(values, default=0))
        high = max(max(values, default=1), threshold or 0, 1 if not self.is_score and self.channel < 2 else 1e-6) * 1.08
        def px(t):
            return box.left() + (t - first) / (last - first) * box.width()
        def py(v):
            return box.bottom() - (v - low) / (high - low) * box.height()
        # Merge contiguous support, never shade across a missing sample.
        for flags, color, height in ((self.data["method_alarms"][self.method], "#472733", box.height()),
                                    (self.data["labels"] if self.truth else [], "#655332", 12)):
            runs = []
            for now, flag in zip(times, flags):
                if flag:
                    if runs and now == runs[-1][1]:
                        runs[-1][1] = now + 50
                    else:
                        runs.append([now, now + 50])
            for start, end in runs:
                p.fillRect(QRectF(px(start), box.bottom() - height,
                                 max(1, px(min(end, last)) - px(start)), height), QColor(color))
        p.setFont(QFont("Consolas", 9))
        for i in range(5):
            value = low + (high - low) * i / 4
            y = py(value)
            p.setPen(QPen(QColor("#223042"), 1))
            p.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
            p.setPen(QColor(MUTED))
            p.drawText(QPointF(8, y + 4), f"{value:.2f}")
        if threshold is not None:
            p.setPen(QPen(QColor(RED), 1.5, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(box.left(), py(threshold)), QPointF(box.right(), py(threshold)))
        for values, color, stepped in self.series():
            path, previous, prior_ms = QPainterPath(), None, None
            for now, value in zip(times, values):
                if value is None:
                    previous = None
                    continue
                point = QPointF(px(now), py(value))
                if previous is None or now - prior_ms != 50:
                    path.moveTo(point)
                else:
                    if stepped:
                        path.lineTo(QPointF(point.x(), previous.y()))
                    path.lineTo(point)
                previous, prior_ms = point, now
            p.setPen(QPen(QColor(color), 1.7))
            p.drawPath(path)
        p.setPen(QPen(QColor("#c1cfdf"), 1, Qt.PenStyle.DotLine))
        p.drawLine(QPointF(px(times[self.cursor]), box.top()), QPointF(px(times[self.cursor]), box.bottom()))
        p.setPen(QColor(MUTED))
        for i in range(6):
            now = first + (last - first) * i / 5
            p.drawText(QPointF(px(now) - 15, box.bottom() + 22), f"{now / 1000:g} s")
        p.end()

    def mousePressEvent(self, event):
        if self.data is not None:
            times = self.data["logical_ms"]
            fraction = max(0, min(1, (event.position().x() - self.box().left()) / self.box().width()))
            now = times[0] + fraction * (times[-1] - times[0])
            self.selected.emit(min(range(len(times)), key=lambda i: abs(times[i] - now)))
        super().mousePressEvent(event)


class MLResultsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data, self.worker, self.path = None, None, None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll)
        root = QVBoxLayout(body)
        root.setContentsMargins(20, 14, 20, 14)
        root.setSpacing(14)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Laboratorium ML")
        title.setObjectName("hero")
        titles.addWidget(title)
        subtitle = QLabel("Zapisany eksperyment  /  pomiar → prognoza → alarm")
        subtitle.setObjectName("muted")
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        badge = QLabel("WYNIKI OFFLINE")
        badge.setObjectName("badge")
        header.addWidget(badge)
        self.open = QPushButton("Otwórz wyniki…")
        self.open.setObjectName("primary")
        self.open.clicked.connect(self.open_dialog)
        header.addWidget(self.open)
        root.addLayout(header)
        self.status = QLabel("Wybierz plik z katalogu timelines. Wykresy pokażą dane zapisane przez eksperyment.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.status)
        controls = QHBoxLayout()
        self.sessions, self.method, self.channel = QComboBox(), QComboBox(), QComboBox()
        self.sessions.setMinimumWidth(260)
        self.sessions.setPlaceholderText("Wybierz zapisaną sesję")
        self.method.setPlaceholderText("Metoda detekcji")
        self.sessions.setAccessibleName("Zapisana sesja ML")
        self.sessions.currentIndexChanged.connect(self.choose_session)
        self.method.setAccessibleName("Metoda detekcji")
        self.method.currentIndexChanged.connect(self.refresh)
        self.channel.addItems(CHANNEL_NAMES)
        self.channel.setCurrentIndex(1)
        self.channel.setAccessibleName("Kanał pomiaru i prognozy")
        self.channel.currentIndexChanged.connect(self.refresh)
        self.truth = QCheckBox("Pokaż etykiety eksperymentu")
        self.truth.setToolTip("Osobna wiedza z symulatora; nie była wejściem detektora. Kolor bursztynowy.")
        self.truth.toggled.connect(self.refresh)
        for widget in (self.sessions, self.method, self.channel, self.truth):
            controls.addWidget(widget, 2 if widget is self.sessions else 1)
        root.addLayout(controls)
        cards = QHBoxLayout()
        self.card_values = []
        for name in ("PRÓBKI", "CZAS OCENY", "PRÓG METODY", "POCZĄTKI ALARMÓW"):
            card = QFrame()
            card.setObjectName("metricCard")
            layout = QVBoxLayout(card)
            caption = QLabel(name)
            caption.setObjectName("muted")
            value = QLabel("—")
            value.setObjectName("metricValue")
            layout.addWidget(caption)
            layout.addWidget(value)
            self.card_values.append(value)
            cards.addWidget(card, 1)
        root.addLayout(cards)
        content = QSplitter(Qt.Orientation.Horizontal)
        charts = QWidget()
        chart_layout = QVBoxLayout(charts)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(12)
        self.measurement, self.score = ResearchPlot(), ResearchPlot(scores=True)
        for plot in (self.measurement, self.score):
            plot.selected.connect(self.set_cursor)
            chart_layout.addWidget(plot, 1)
        content.addWidget(charts)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 0, 0, 0)
        label = QLabel("DOWODY W WYBRANEJ CHWILI")
        label.setObjectName("section")
        side.addWidget(label)
        self.evidence = QPlainTextEdit("Przesuń kursor na wykresie.")
        self.evidence.setReadOnly(True)
        self.evidence.setMinimumHeight(210)
        self.evidence.setObjectName("evidence")
        side.addWidget(self.evidence)
        label = QLabel("OŚ POLECEŃ · kliknij, aby przejść")
        label.setObjectName("section")
        side.addWidget(label)
        self.commands = table(["Czas", "Nastawa"])
        self.commands.setMinimumHeight(145)
        self.commands.verticalHeader().setDefaultSectionSize(25)
        self.commands.setAccessibleName("Oś czasu wysłanych poleceń")
        self.commands.cellClicked.connect(self.command_cursor)
        side.addWidget(self.commands, 1)
        legend = QLabel("Różowy pas: aktywny alarm wybranej metody.\nBursztynowy pas: etykieta, gdy ją włączysz.\n\nBrak próbki przerywa linię wykresu.")
        legend.setWordWrap(True)
        legend.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        legend.setObjectName("muted")
        side.addWidget(legend)
        content.addWidget(sidebar)
        content.setSizes([980, 290])
        content.setChildrenCollapsible(False)
        root.addWidget(content, 1)
        cursor_bar = QHBoxLayout()
        self.time = QLabel("t = —")
        self.time.setMinimumWidth(110)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setAccessibleName("Czas analizowanej próbki")
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self.refresh)
        cursor_bar.addWidget(self.time)
        cursor_bar.addWidget(self.slider, 1)
        outer.addLayout(cursor_bar)
        self.provenance = QLabel("Brak wczytanego modelu na żywo. Ten widok odczytuje pliki wynikowe.")
        self.provenance.setObjectName("muted")
        self.provenance.setWordWrap(True)
        self.provenance.setTextFormat(Qt.TextFormat.PlainText)
        outer.addWidget(self.provenance)

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Otwórz oś czasu ML", "experiments/runs", "Oś czasu JSON (*.json)")
        if path:
            self.load_timeline(path)

    def choose_session(self, index):
        path = self.sessions.itemData(index)
        if path and Path(path) != self.path:
            self.load_timeline(path)

    def load_timeline(self, path):
        if self.worker is not None:
            return
        self.status.setText("Wczytywanie i sprawdzanie osi czasu…")
        self.open.setEnabled(False)
        self.sessions.setEnabled(False)
        self.worker = TimelineWorker(path, self)
        self.worker.result.connect(self.loaded)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    @Slot(object, str)
    def loaded(self, data, error):
        if error:
            self.status.setText(f"Nie wczytano wyników: {error}")
            return
        self.data, self.path = data, self.worker.path
        with QSignalBlocker(self.sessions), QSignalBlocker(self.method):
            self.sessions.clear()
            siblings = sorted(self.path.parent.glob("*.json"))[:1000]
            if self.path not in siblings:
                siblings.append(self.path)
            for path in siblings:
                name = path.stem
                if name.startswith("calibration-v1-evaluation-"):
                    parts = name.removeprefix("calibration-v1-evaluation-").split("-", 2)
                    if len(parts) == 3:
                        condition, seed, case = parts
                        name = f"Seed {seed} · {CONDITION_NAMES.get(condition, condition)} · {CASE_NAMES.get(case, case)}"
                self.sessions.addItem(name, str(path))
            self.sessions.setCurrentIndex(self.sessions.findData(str(self.path)))
            self.method.clear()
            for method in data["scores"]:
                self.method.addItem(METHOD_NAMES[method], method)
            self.method.setCurrentIndex(0)
        fill_table(self.commands, [(f"{c['logical_ms'] / 1000:g} s", "Otwórz · 110°" if c["value"] else "Zamknij · 0°") for c in data["commands"]])
        self.slider.setRange(0, len(data["logical_ms"]) - 1)
        self.slider.setEnabled(True)
        self.slider.setValue(0)
        condition = data.get("condition", data.get("profile", "sesja"))
        case, policy = data.get("case", "brak opisu"), data.get("policy", "próg kroku 17")
        self.status.setText(f"{CONDITION_NAMES.get(condition, condition)}  ·  {CASE_NAMES.get(case, case)}  ·  Próg: {POLICY_NAMES.get(policy, policy)}")
        source = {"synthetic": "Symulacja", "physical": "Sprzęt", "replay": "Odtwarzanie"}.get(data.get("source"), data.get("source", "Symulacja · diagnostyka kroku 17"))
        self.provenance.setText(f"Źródło: {source}  ·  Model: {data.get('model_version', 'GRU · diagnostyka kroku 17')}  ·  Cechy: {data.get('feature_version', 'wersja w manifeście eksperymentu')}\n{self.path.name}")
        self.provenance.setToolTip(str(self.path))
        self.refresh()

    @Slot()
    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.open.setEnabled(True)
        self.sessions.setEnabled(True)

    def set_cursor(self, index):
        self.slider.setValue(index)

    def command_cursor(self, row, column):
        if self.data is not None:
            now = self.data["commands"][row]["logical_ms"]
            self.set_cursor(min(range(len(self.data["logical_ms"])), key=lambda i: abs(self.data["logical_ms"][i] - now)))

    def refresh(self, *args):
        if self.data is None or self.method.currentData() is None:
            return
        data, method, i = self.data, self.method.currentData(), self.slider.value()
        flags = data["method_alarms"][method]
        starts = sum(flag and (j == 0 or not flags[j - 1] or data["logical_ms"][j] - data["logical_ms"][j - 1] != 50) for j, flag in enumerate(flags))
        for label, value in zip(self.card_values, (len(flags), f"{(data['logical_ms'][-1] - data['logical_ms'][0]) / 1000:g} s", f"{data['thresholds'][method]:.3f}", starts)):
            label.setText(str(value))
        self.time.setText(f"t = {data['logical_ms'][i] / 1000:.2f} s")
        def fmt(value):
            return "brak danych" if value is None else f"{value:.4f}"
        channel = self.channel.currentIndex()
        residual = data["scaled_residuals"][i]
        valid = [(v, j) for j, v in enumerate(residual) if v is not None]
        largest = CHANNEL_NAMES[max(valid)[1]] if valid else "brak danych"
        text = (f"{CHANNEL_NAMES[channel]}\nPomiar: {fmt(data['actual'][i][channel])}\nPrognoza GRU: {fmt(data['predicted'][i][channel])}\n\n"
                f"{METHOD_NAMES[method]}: {fmt(data['scores'][method][i])}\nPróg: {data['thresholds'][method]:.4f}\nAlarm: {'AKTYWNY' if flags[i] else 'nieaktywny'}\n"
                f"Oczekujące polecenia: {data['pending_commands'][i]}\n\nNajwiększy błąd GRU:\n{largest}\nWskazówka, nie dowód przyczyny.")
        if self.truth.isChecked():
            text += f"\n\nEtykieta eksperymentu: {data['labels'][i]}"
        self.evidence.setPlainText(text)
        for plot in (self.measurement, self.score):
            plot.data, plot.channel, plot.method, plot.cursor, plot.truth = data, channel, method, i, self.truth.isChecked()
            plot.update()
