"""Telemetry plot; gaps never interpolate a missing device message."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

BG, GRID, TEXT, MUTED, BLUE, GREEN, AMBER = "#030507", "#19212c", "#dce3ec", "#8d9bac", "#75b8fa", "#73d4b5", "#e9bd6a"


class SignalPlot(QWidget):
    def __init__(self, sim):
        super().__init__()
        self.sim = sim
        self.sensor = "gas_01"
        self.setMinimumSize(400, 160)
        self.setAccessibleName("Telemetria gas_01; próg i przerwy w wiadomościach")

    def samples(self):
        node = self.sim.components[self.sensor]["node"]
        recent = {m["sequence_number"]: m["sensors"][self.sensor]["value"]
                  for m in self.sim.history if m["device_id"] == node}
        return [(tick, recent.get(tick)) for tick in range(max(0, self.sim.time - 120), self.sim.time)]

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        box = QRectF(50, 30, self.width() - 72, self.height() - 65)
        samples = self.samples()
        first, last = samples[0][0], max(samples[0][0] + 10, samples[-1][0])
        p.setFont(QFont("Consolas", 10))
        p.setPen(QColor(TEXT))
        p.drawText(15, 18, f"{self.sensor}  /  TELEMETRIA [0–1]")
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
        p.setPen(QPen(QColor(GREEN), 2))
        p.drawPath(path)
        p.setBrush(QColor(GREEN))
        for point in points:
            p.drawEllipse(point, 2, 2)
