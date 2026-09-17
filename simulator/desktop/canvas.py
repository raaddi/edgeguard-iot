"""Qt drawings: clickable garage and a telemetry trace with explicit gaps."""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

BG, GRID, TEXT, MUTED, BLUE, GREEN, AMBER = "#171d24", "#252e38", "#dce3ec", "#8d9bac", "#75b8fa", "#73d4b5", "#e9bd6a"


class GarageCanvas(QWidget):
    selected = Signal(str)
    # Logical coordinates remain independent of window size and model node mapping.
    AREAS = {
        "gas_01": QRectF(70, 70, 158, 66),
        "fan_01": QRectF(562, 70, 158, 66),
        "led_01": QRectF(70, 223, 128, 64),
        "led_02": QRectF(592, 223, 128, 64),
        "servo_01": QRectF(174, 414, 206, 52),
        "servo_02": QRectF(410, 414, 206, 52),
    }

    def __init__(self, sim):
        super().__init__()
        self.sim, self.current = sim, "gas_01"
        self.setMinimumSize(400, 280)
        self.setAccessibleName("Klikalny schemat garażu; urządzenia dostępne także na liście po prawej")
        self.setToolTip("Kliknij czujnik, wentylator, światło lub skrzydło bramy. Sterowanie jest po prawej.")

    def transform_geometry(self):
        scale = min(self.width() / 790, self.height() / 505)
        return scale, (self.width() - 790 * scale) / 2, (self.height() - 505 * scale) / 2

    def device_center(self, cid):
        scale, x, y = self.transform_geometry()
        center = self.AREAS[cid].center()
        return QPointF(x + center.x() * scale, y + center.y() * scale).toPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scale, x, y = self.transform_geometry()
            point = QPointF((event.position().x() - x) / scale, (event.position().y() - y) / scale)
            for cid, rect in self.AREAS.items():
                if rect.contains(point):
                    self.selected.emit(cid)
                    return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        scale, x, y = self.transform_geometry()
        p.translate(x, y)
        p.scale(scale, scale)
        p.setPen(QPen(QColor(GRID), 1))
        for gx in range(20, 790, 25):
            p.drawLine(gx, 20, gx, 485)
        for gy in range(20, 490, 25):
            p.drawLine(20, gy, 770, gy)
        p.setPen(QPen(QColor("#6f7e8d"), 5))
        p.drawPolyline([QPointF(45, 432), QPointF(45, 45), QPointF(745, 45), QPointF(745, 432)])
        p.drawLine(45, 432, 162, 432)
        p.drawLine(628, 432, 745, 432)
        p.setPen(QColor(MUTED))
        p.setFont(QFont("Segoe UI", 12))
        p.drawText(QRectF(235, 58, 320, 32), Qt.AlignmentFlag.AlignCenter, "GARAŻ / widok funkcjonalny")
        # A quiet parking outline establishes orientation without fake instrumentation.
        p.setPen(QPen(QColor("#394654"), 2))
        p.setBrush(QColor("#1c242e"))
        p.drawRoundedRect(QRectF(304, 157, 182, 219), 28, 28)
        p.drawRoundedRect(QRectF(321, 192, 148, 57), 10, 10)
        p.drawLine(321, 330, 469, 330)
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(305, 275, 180, 30), Qt.AlignmentFlag.AlignCenter, "STREFA PARKOWANIA")
        for cid, rect in self.AREAS.items():
            c = self.sim.components[cid]
            if c["kind"] == "gas":
                value = self.sim.sensors[cid]["value"]
                state = f"{value:.3f} / 0–1"
                color = AMBER if value > self.sim.profile["threshold"] else GREEN
            else:
                value = self.sim.actuators[cid]["simulated"]
                state = f"{value}°" if c["kind"] == "servo" else "ON" if value else "OFF"
                color = GREEN if value else MUTED
            selected = cid == self.current
            p.setBrush(QColor("#243b52" if selected else "#202a35"))
            p.setPen(QPen(QColor(BLUE if selected else "#506172"), 2 if selected else 1))
            p.drawRoundedRect(rect, 4, 4)
            p.setPen(QColor(TEXT))
            p.setFont(QFont("Consolas", 11))
            p.drawText(rect.adjusted(10, 5, -8, -28), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, cid)
            p.setPen(QColor(color))
            p.drawText(rect.adjusted(10, 28, -8, -3), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, state)
        p.setPen(QColor(MUTED))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(QRectF(180, 476, 430, 20), Qt.AlignmentFlag.AlignCenter, "WJAZD  /  dwa skrzydła bramy")


class SignalPlot(QWidget):
    def __init__(self, sim):
        super().__init__()
        self.sim = sim
        self.setMinimumSize(400, 160)
        self.setAccessibleName("Telemetria gas_01; próg i przerwy w wiadomościach")

    def samples(self):
        node = self.sim.components["gas_01"]["node"]
        recent = {m["sequence_number"]: m["sensors"]["gas_01"]["value"]
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
        p.drawText(15, 18, "gas_01  •  wyemitowana telemetria [0–1]")
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
