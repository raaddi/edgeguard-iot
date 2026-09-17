"""House overview and room close-up drawn from the shared component profile."""

from math import ceil
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

COLORS = {"gas": "#49d7ff", "fan": "#5cedab", "light": "#ffd366", "servo": "#b795ff"}
KINDS = {"gas": "CZUJNIK", "fan": "WENTYLATOR", "light": "ŚWIATŁO", "servo": "SERWO"}


class HouseCanvas(QWidget):
    selected = Signal(str)
    room_selected = Signal(str)

    def __init__(self, sim):
        super().__init__()
        self.sim, self.current, self.room = sim, "gas_01", None
        self.setMinimumSize(360, 270)
        self.setAccessibleName("Makieta SmartHome; wybór urządzeń również w drzewie instalacji")
        self.setToolTip("Kliknij urządzenie. Dwuklik w pomieszczenie otwiera zbliżenie.")

    def rooms(self):
        return self.sim.profile["rooms"] + ([{"id": "virtual", "name": "Węzły wirtualne", "rect": [50, 760, 660, 150]}] if self.sim.extra_nodes else [])

    def areas(self):
        areas = {}
        for room in self.rooms():
            if self.room and room["id"] != self.room:
                continue
            x, y, w, h = [20, 20, 750, 455] if self.room else room["rect"]
            devices = [cid for cid, c in self.sim.components.items() if c["room"] == room["id"]]
            cols = min(3, max(1, int(w // (210 if self.room else 85))))
            rows = max(1, ceil(len(devices) / cols))
            cell_w, cell_h = (w - 20) / cols, (h - 45) / rows
            for i, cid in enumerate(devices):
                areas[cid] = QRectF(x + 10 + (i % cols) * cell_w, y + 37 + (i // cols) * cell_h,
                                   cell_w - 7, min(cell_h - 6, 76) if not self.room else cell_h - 6)
        return areas

    def transform_geometry(self):
        w, h = (790, 500) if self.room else (760, 940 if self.sim.extra_nodes else 780)
        scale = min(self.width() / w, self.height() / h)
        return scale, (self.width() - w * scale) / 2, (self.height() - h * scale) / 2

    def device_center(self, cid):
        scale, x, y = self.transform_geometry()
        center = self.areas()[cid].center()
        return QPointF(x + center.x() * scale, y + center.y() * scale).toPoint()

    def logical_point(self, position):
        scale, x, y = self.transform_geometry()
        return QPointF((position.x() - x) / scale, (position.y() - y) / scale)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            for cid, rect in self.areas().items():
                if rect.contains(self.logical_point(event.position())):
                    self.selected.emit(cid)
                    return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if not self.room:
            for room in self.rooms():
                if QRectF(*room["rect"]).contains(self.logical_point(event.position())):
                    self.room_selected.emit(room["id"])
                    return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#030507"))
        scale, x, y = self.transform_geometry()
        p.translate(x, y)
        p.scale(scale, scale)
        areas = self.areas()
        for room in self.rooms():
            if self.room and room["id"] != self.room:
                continue
            rect = QRectF(20, 20, 750, 455) if self.room else QRectF(*room["rect"])
            chosen = self.sim.components[self.current]["room"] == room["id"]
            p.setBrush(QColor("#0a141c" if chosen else "#090d12"))
            p.setPen(QPen(QColor("#49d7ff" if chosen else "#3a4654"), 2))
            p.drawRect(rect.adjusted(2, 2, -2, -2))
            p.setPen(QColor("#e4edf7"))
            p.setFont(QFont("Segoe UI", 16))
            name = "Pokój*" if room["id"] == "room" and not self.room else room["name"]
            p.drawText(rect.adjusted(12, 4, -5, -rect.height() + 30), Qt.AlignmentFlag.AlignVCenter, name)
            if not any(c["room"] == room["id"] for c in self.sim.components.values()):
                p.setPen(QColor("#8795a7"))
                p.setFont(QFont("Segoe UI", 13))
                p.drawText(rect.adjusted(12, 40, -12, -12), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, "Brak urządzeń w profilu")
        for cid, rect in areas.items():
            component = self.sim.components[cid]
            online = self.sim.nodes[component["node"]]
            color = COLORS[component["kind"]] if online else "#ff657a"
            if component["kind"] == "gas":
                value = self.sim.sensors[cid]["value"]
                state = f"{value:.3f}"
                if online and value > self.sim.profile["threshold"]:
                    color = "#ffaf45"
            else:
                state_value = self.sim.actuators[cid]["simulated"]
                state = f"{state_value}°" if component["kind"] == "servo" else "ON" if state_value else "OFF"
            selected = cid == self.current
            p.setBrush(QColor("#153043" if selected else "#0d141c"))
            p.setPen(QPen(QColor(color if selected else "#273744"), 2 if selected else 1))
            p.drawRoundedRect(rect, 3, 3)
            p.setFont(QFont("Consolas", 15 if self.room else 12))
            p.setPen(QColor(color))
            if self.room:
                p.drawText(rect.adjusted(10, 7, -5, -rect.height() + 30), cid)
                p.setFont(QFont("Segoe UI", 12))
                p.drawText(rect.adjusted(10, 34, -5, -25), Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, component["name"])
                p.setFont(QFont("Consolas", 18))
                p.drawText(rect.adjusted(10, rect.height() - 40, -5, -5), state if online else f"{state} / OFFLINE")
            else:
                short = cid.replace("virtual_gas_", "V").replace("gas_", "G").replace("fan_", "F").replace("led_", "L").replace("servo_", "S")
                p.drawText(rect.adjusted(4, 1, -1, -1), Qt.AlignmentFlag.AlignCenter, f"{short} {state}")
        if not self.room:
            p.setPen(QColor("#8090a3"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(50, 735, 660, 22), Qt.AlignmentFlag.AlignCenter, "FRONT / WJAZD    ·    * przypisanie pokoju do potwierdzenia")
