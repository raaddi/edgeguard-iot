"""Read-only collector workspace: no HouseSimulation or inferred node liveness."""

from datetime import datetime, timezone
import json
import re
from urllib.parse import urlencode

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from contracts.telemetry import validate_telemetry
from simulator.desktop.api_client import ApiClient
from simulator.desktop.canvas import BG, GRID, MUTED, AMBER, SignalPlot
from simulator.desktop.house_canvas import COLORS
from simulator.desktop.panels import table, fill_table


def channel_samples(records, cid, field="reported"):
    """Sequence axis within one boot; missing messages/reports break the trace."""
    samples, previous = [], None
    for record in sorted(records, key=lambda r: r["telemetry"]["sequence_number"]):
        message = record["telemetry"]
        sequence = message["sequence_number"]
        if previous is not None and sequence != previous + 1:
            samples.append((sequence, None))
        value = (message["sensors"][cid]["value"] if cid in message["sensors"]
                 else message["actuators"].get(cid, {}).get(field))
        samples.append((sequence, value))
        previous = sequence
    return samples


class HistoryPlot(QWidget):
    def __init__(self, records, cid, kind, parent=None):
        super().__init__(parent)
        self.records, self.cid, self.kind = records, cid, kind
        self.setMinimumSize(220, 170)
        self.setAccessibleName(f"Historia kolektora: {cid}")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        color = COLORS[self.kind]
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor(color))
        p.drawText(8, 19, p.fontMetrics().elidedText(self.cid, Qt.TextElideMode.ElideRight, self.width()-16))
        box = QRectF(40, 40, self.width()-55, self.height()-76)
        samples = channel_samples(self.records, self.cid)
        first, last = samples[0][0], max(samples[0][0] + 1, samples[-1][0])
        scale = 180 if self.kind == "servo" else 1
        for value in (0, scale):
            y = box.bottom() - value / scale * box.height()
            p.setPen(QPen(QColor(GRID), 1))
            p.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
            p.setPen(QColor(MUTED))
            label = f"{value}°" if self.kind == "servo" else str(value) if self.kind == "gas" else "ON" if value else "OFF"
            p.drawText(QPointF(3, y + 4), label)
        p.drawText(QPointF(box.left(), box.bottom()+25), str(first))
        p.drawText(QPointF(box.right()-70, box.bottom()+25), f"seq {last}")
        fields = [("commanded", AMBER, Qt.PenStyle.DashLine)] if self.kind != "gas" else []
        fields.append(("reported", color, Qt.PenStyle.SolidLine))
        for field, shade, style in fields:
            path, points = SignalPlot.trace(channel_samples(self.records, self.cid, field), box,
                                            first, last, scale, self.kind != "gas")
            p.setPen(QPen(QColor(shade), 3 if field == "commanded" else 2, style))
            p.drawPath(path)
            p.setBrush(QColor(shade))
            for point in points:
                p.drawEllipse(point, 2, 2)


class CollectorView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = ApiClient(self)
        self.client.result.connect(self.received)
        self.records, self.plots, self.next_device = [], {}, ""
        self.last_success = None
        self.older_available = False
        self.plot_key = None
        root = QVBoxLayout(self)
        title = QLabel("EDGEGUARD  /  Historia kolektora")
        title.setObjectName("brand")
        root.addWidget(title)
        note = QLabel("ODCZYT Z SQLITE PRZEZ API · historia nie potwierdza obecności węzła online · brak sterowania")
        note.setWordWrap(True)
        root.addWidget(note)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("127.0.0.1 · port"))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(8000)
        self.port.setAccessibleName("Port API kolektora")
        self.port.valueChanged.connect(self.reset_connection)
        bar.addWidget(self.port)
        self.connect_button = QPushButton("Połącz / lista węzłów")
        self.connect_button.clicked.connect(lambda: self.load_devices())
        bar.addWidget(self.connect_button)
        self.next_button = QPushButton("Następne węzły")
        self.next_button.setEnabled(False)
        self.next_button.clicked.connect(lambda: self.load_devices(self.next_device))
        bar.addWidget(self.next_button)
        self.nodes = QComboBox()
        self.nodes.setAccessibleName("Węzeł kolektora")
        self.nodes.currentIndexChanged.connect(self.select_node)
        bar.addWidget(self.nodes, 1)
        root.addLayout(bar)
        second = QHBoxLayout()
        self.refresh_button = QPushButton("Odśwież dane")
        self.refresh_button.clicked.connect(self.load_records)
        second.addWidget(self.refresh_button)
        self.auto = QCheckBox("Odświeżaj co 5 s")
        second.addWidget(self.auto)
        second.addWidget(QLabel("Sesja uruchomienia (boot_id):"))
        self.boots = QComboBox()
        self.boots.currentIndexChanged.connect(self.render_records)
        second.addWidget(self.boots, 1)
        root.addLayout(second)
        self.status, self.receipt = QLabel("Nie połączono z API."), QLabel("Brak pobranych danych.")
        for label in (self.status, self.receipt):
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            root.addWidget(label)
        legend = QLabel("Gaz: 0–1, nie ppm. Aktuatory: przerywana = zadane, ciągła = raport. Oś X: numer wiadomości w jednej sesji.")
        legend.setWordWrap(True)
        legend.setObjectName("muted")
        root.addWidget(legend)
        self.charts = QScrollArea()
        self.charts.setWidgetResizable(True)
        self.values = table(["Komponent", "Zadane", "Raport / wartość", "Źródło / status"])
        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        tabs = QTabWidget()
        tabs.addTab(self.values, "Ostatni raport sesji")
        tabs.addTab(self.raw, "Telemetria JSON")
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.charts)
        split.addWidget(tabs)
        split.setSizes([500, 180])
        root.addWidget(split, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.poll)
        self.auto.toggled.connect(lambda enabled: self.timer.start() if enabled else self.timer.stop())
        self.refresh_button.setEnabled(False)

    def clear_records(self):
        self.records = []
        self.boots.clear()
        self.render_records()

    def stop(self):
        self.auto.setChecked(False)
        self.client.cancel()
        self.status.setText("Odczyt zatrzymany. Wyświetlane dane to ostatnio pobrana historia.")

    def reset_connection(self):
        self.stop()
        self.nodes.clear()
        self.next_device = ""
        self.next_button.setEnabled(False)
        self.clear_records()
        self.last_success = None
        self.status.setText("Zmieniono port. Połącz z API.")

    def load_devices(self, after=""):
        self.auto.setChecked(False)
        self.client.cancel()
        self.nodes.clear()
        self.clear_records()
        self.next_button.setEnabled(False)
        self.status.setText("Pobieranie listy węzłów…")
        self.client.get(self.port.value(), "/devices?" + urlencode({"limit": 200, "after_device": after}), "devices")

    def select_node(self):
        self.client.cancel()
        self.clear_records()
        self.refresh_button.setEnabled(bool(self.nodes.currentData()))
        self.load_records()

    def load_records(self):
        node = self.nodes.currentData()
        if node:
            self.status.setText("Pobieranie ostatnich raportów…")
            self.client.get(self.port.value(), f"/devices/{node}/telemetry/recent?limit=200", node)

    def poll(self):
        if self.client.reply is None and self.isVisible():
            self.load_records()

    def received(self, tag, data, error):
        if error:
            self.status.setText(error + " Wyświetlane dane nie zostały odświeżone.")
            return
        try:
            items = data["items"]
            if not isinstance(items, list) or len(items) > 200:
                raise ValueError()
            if tag == "devices":
                ids = [item["device_id"] for item in items]
                if any(not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cid) for cid in ids):
                    raise ValueError()
                if len(set(ids)) != len(ids) or type(data['has_more']) is not bool:
                    raise ValueError()
                cursor = data['next_after_device']
                if not isinstance(cursor, str) or (data['has_more'] and (not ids or cursor != ids[-1])):
                    raise ValueError()
                self.next_device = cursor
                self.next_button.setEnabled(data['has_more'])
                self.nodes.blockSignals(True)
                for cid in ids:
                    self.nodes.addItem(cid, cid)
                self.nodes.blockSignals(False)
                self.status.setText(f"API dostępne · węzły na stronie: {len(ids)}. Status online nieznany.")
                self.select_node()
            elif tag == self.nodes.currentData():
                if type(data['older_available']) is not bool:
                    raise ValueError()
                previous = 0
                channels = {}
                for item in items:
                    message = item['telemetry']
                    validate_telemetry(message, topic=item['topic'])
                    if message['device_id'] != tag or type(item['id']) is not int or item['id'] <= previous:
                        raise ValueError()
                    received = datetime.fromisoformat(item['received_at'].replace('Z', '+00:00'))
                    if received.utcoffset() is None:
                        raise ValueError()
                    boot = message['boot_id']
                    kinds = channels.setdefault(boot, {})
                    incoming = {cid: 'gas' for cid in message['sensors']}
                    incoming.update({cid: a['kind'] for cid, a in message['actuators'].items()})
                    if any(cid in kinds and kinds[cid] != kind for cid, kind in incoming.items()):
                        raise ValueError()
                    kinds.update(incoming)
                    if len(kinds) > 128:
                        raise ValueError()
                    previous = item['id']
                old_boot = self.boots.currentData()
                self.records, self.older_available = items, data['older_available']
                self.last_success = datetime.now(timezone.utc)
                boots = list(dict.fromkeys(r['telemetry']['boot_id'] for r in reversed(items)))
                self.boots.blockSignals(True)
                self.boots.clear()
                for boot in boots:
                    self.boots.addItem(boot, boot)
                index = self.boots.findData(old_boot)
                self.boots.setCurrentIndex(max(index, 0))
                self.boots.blockSignals(False)
                self.render_records()
                self.status.setText(f"API dostępne · odczyt UTC {self.last_success:%H:%M:%S} · {len(items)} raportów"
                                    + (" · starsze dane pozostają w bazie" if self.older_available else ""))
        except (KeyError, TypeError, ValueError, AttributeError):
            self.status.setText("Niepoprawna odpowiedź API. Zachowano poprzedni podgląd; dane nie zostały odświeżone.")

    def render_records(self):
        if not hasattr(self, 'charts'):
            return
        records = [r for r in self.records if r['telemetry']['boot_id'] == self.boots.currentData()]
        panel = QWidget()
        grid = QGridLayout(panel)
        replace_plots = True
        rows = []
        if records:
            latest = records[-1]
            message = latest['telemetry']
            components = {}
            for record in records:
                components.update({cid: 'gas' for cid in record['telemetry']['sensors']})
                components.update({cid: a['kind'] for cid, a in record['telemetry']['actuators'].items()})
            key = (self.boots.currentData(), tuple(components.items()))
            replace_plots = key != self.plot_key
            if replace_plots:
                self.plots = {}
                for index, (cid, kind) in enumerate(components.items()):
                    plot = HistoryPlot(records, cid, kind)
                    self.plots[cid] = plot
                    grid.addWidget(plot, index // 4, index % 4)
            else:
                for plot in self.plots.values():
                    plot.records = records
                    plot.update()
            self.plot_key = key
            for cid, value in message['sensors'].items():
                rows.append((cid, '—', value['value'] if value['value'] is not None else 'brak', value['status']))
            for cid, value in message['actuators'].items():
                unit = '°' if value['kind'] == 'servo' else ''
                rows.append((cid, f"{value['commanded']}{unit}",
                             f"{value['reported']}{unit}" if value['reported'] is not None else 'brak', value['feedback']))
            self.receipt.setText(f"Ostatni odbiór tej sesji: {latest['received_at']} · czas urządzenia: {message['timestamp'] or 'brak'}\n"
                                 f"Sesja: {message['boot_id']} · {len(records)} raportów w podglądzie. Pochodzenie raportu podano w tabeli.")
            self.raw.setPlainText(json.dumps(latest, ensure_ascii=False, indent=2))
        else:
            self.plot_key, self.plots = None, {}
            grid.addWidget(QLabel("Brak raportów do wyświetlenia. Połącz z API i wybierz węzeł."), 0, 0)
            self.receipt.setText("Brak pobranych danych.")
            self.raw.clear()
        for column in range(4):
            grid.setColumnStretch(column, 1)
        fill_table(self.values, rows)
        if replace_plots:
            previous = self.charts.takeWidget()
            if previous is not None:
                previous.deleteLater()
            self.charts.setWidget(panel)
        else:
            panel.deleteLater()
