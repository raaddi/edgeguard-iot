"""Telemetry plot; gaps never interpolate a missing device message."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGridLayout, QScrollArea, QWidget

BG, GRID, TEXT, MUTED, BLUE, GREEN, AMBER = "#030507", "#19212c", "#dce3ec", "#8d9bac", "#75b8fa", "#73d4b5", "#e9bd6a"


class SignalPlot(QWidget):
    def __init__(self, sim, sensor="gas_01", compact=False, color=GREEN):
        super().__init__()
        self.sim = sim
        self.sensor, self.compact, self.color = sensor, compact, color
        self.setMinimumSize(220 if compact else 400, 180 if compact else 160)
        self.setAccessibleName(f"Telemetria {sensor}; próg i przerwy w wiadomościach")

    def samples(self):
        node = self.sim.components[self.sensor]["node"]
        recent = {m["sequence_number"]: m["sensors"][self.sensor]["value"]
                  for m in self.sim.history if m["device_id"] == node}
        return [(tick, recent.get(tick)) for tick in range(max(0, self.sim.time - 120), self.sim.time)]

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        box = QRectF(40, 54, self.width() - 55, self.height() - 83)
        samples = self.samples()
        first, last = samples[0][0], max(samples[0][0] + 10, samples[-1][0])
        p.setFont(QFont("Segoe UI", 9 if self.compact else 10))
        p.setPen(QColor(self.color))
        name = self.sim.components[self.sensor]["name"]
        title = f"{self.sensor} · {name}"
        p.drawText(10, 17, p.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, self.width() - 20))
        node = self.sim.components[self.sensor]["node"]
        online = self.sim.nodes[node]
        latest = samples[-1][1]
        status = "OFFLINE · brak nowej próbki" if not online else "brak próbki" if latest is None else f"{latest:.3f} / 0–1 · t={self.sim.time - 1} s"
        p.setPen(QColor(MUTED if online else "#ff657a"))
        p.drawText(10, 35, status)
        p.setFont(QFont("Consolas", 9 if self.compact else 10))
        for value in (0.0, 0.5, 1.0):
            y = box.bottom() - value * box.height()
            p.setPen(QPen(QColor(GRID), 1))
            p.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
            p.setPen(QColor(MUTED))
            p.drawText(QPointF(12, y + 4), f"{value:.1f}")
        p.drawText(QPointF(box.left(), box.bottom() + 23), str(first))
        p.drawText(QPointF(box.right() - 60, box.bottom() + 23), f"{last} s")
        threshold_y = box.bottom() - self.sim.profile["threshold"] * box.height()
        p.setPen(QPen(QColor(AMBER), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(box.left(), threshold_y), QPointF(box.right(), threshold_y))
        path, connected = QPainterPath(), False
        points = []
        for tick, value in samples:
            if value is None:
                connected = False
                continue
            point = QPointF(box.left() + (tick - first) / (last - first) * box.width(), box.bottom() - value * box.height())
            if connected:
                path.lineTo(point)
            else:
                path.moveTo(point)
            connected = True
            points.append(point)
        p.setPen(QPen(QColor(self.color), 2))
        p.drawPath(path)
        p.setBrush(QColor(self.color))
        for point in points:
            p.drawEllipse(point, 2, 2)


class SignalGrid(QScrollArea):
    """Same time and value scales across every sensor, independent of selection."""

    COLORS = ["#49d7ff", "#5cedab", "#b795ff", "#ffd366"]

    def __init__(self, sim):
        super().__init__()
        self.setWidgetResizable(True)
        self.setMinimumHeight(190)
        self.setAccessibleName("Wykresy wszystkich czujników całej makiety")
        self.set_simulation(sim)

    def set_simulation(self, sim):
        previous = self.takeWidget()
        if previous is not None:
            previous.deleteLater()
        panel = QWidget()
        self.grid = QGridLayout(panel)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setSpacing(6)
        self.plots = {}
        for index, cid in enumerate(sim.sensors):
            plot = SignalPlot(sim, cid, compact=True, color=self.COLORS[index % len(self.COLORS)])
            plot.setToolTip(f"{sim.components[cid]['name']} / {sim.components[cid]['node']}\nTelemetria 0–1, próg reguły zaznaczony przerywaną linią. Nie jest to pomiar ppm.")
            self.plots[cid] = plot
            self.grid.addWidget(plot, index // 4, index % 4)
        for column in range(4):
            self.grid.setColumnStretch(column, 1)
        self.setWidget(panel)

    def refresh(self):
        for plot in self.plots.values():
            plot.update()
