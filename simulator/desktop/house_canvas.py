"""House overview and room close-up drawn from the shared component profile."""

from math import ceil
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QToolTip, QWidget

COLORS = {"gas": "#8bb7c9", "fan": "#91b39d", "light": "#d1bc8b", "servo": "#b1a1c7"}
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

    def state_text(self, cid):
        component = self.sim.components[cid]
        if component["kind"] == "gas":
            return f"{self.sim.sensors[cid]['value']:.3f}"
        value = self.sim.actuators[cid]["simulated"]
        return f"{value}°" if component["kind"] == "servo" else "ON" if value else "OFF"

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            point = self.logical_point(event.pos())
            for cid, rect in self.areas().items():
                if rect.contains(point):
                    component = self.sim.components[cid]
                    online = self.sim.nodes[component["node"]]
                    status = "ONLINE / model" if online else "OFFLINE / stan modelu"
                    text = (f"{cid} · {component['name']}\n{component['node']}\n"
                            f"{self.state_text(cid)} · {status}\n"
                            "Kliknij, aby zobaczyć szczegóły w panelu urządzenia.")
                    QToolTip.showText(event.globalPos(), text, self)
                    return True
            QToolTip.showText(event.globalPos(), self.toolTip(), self)
            return True
        return super().event(event)

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
        background = QLinearGradient(0, 0, self.width(), self.height())
        background.setColorAt(0, QColor("#1c2026"))
        background.setColorAt(1, QColor("#101216"))
        p.fillRect(self.rect(), background)
        scale, x, y = self.transform_geometry()
        p.translate(x, y)
        p.scale(scale, scale)
        areas = self.areas()
        for room in self.rooms():
            if self.room and room["id"] != self.room:
                continue
            rect = QRectF(20, 20, 750, 455) if self.room else QRectF(*room["rect"])
            chosen = self.sim.components[self.current]["room"] == room["id"]
            room_surface = QLinearGradient(rect.topLeft(), rect.bottomRight())
            room_surface.setColorAt(0, QColor("#292b2e" if chosen else "#24272c"))
            room_surface.setColorAt(1, QColor("#1b1b1c" if chosen else "#171a1f"))
            p.setBrush(room_surface)
            p.setPen(QPen(QColor("#bd916f" if chosen else "#484b50"), 2))
            p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 8, 8)
            metal = QLinearGradient(rect.topLeft(), rect.topRight())
            metal.setColorAt(0, QColor("#866b56" if chosen else "#484c52"))
            metal.setColorAt(0.5, QColor("#b29379" if chosen else "#777b80"))
            metal.setColorAt(1, QColor("#614d3e" if chosen else "#353940"))
            p.setPen(QPen(QBrush(metal), 1))
            p.drawLine(rect.topLeft() + QPointF(12, 31), rect.topRight() + QPointF(-12, 31))
            p.setPen(QColor("#e8e4de"))
            room_font = QFont("Segoe UI")
            title_rect = rect.adjusted(12, 4, -5, -rect.height() + 30)
            room_font.setPixelSize(min(round(max(20, 10 / scale)), int(title_rect.height() * 0.8)))
            p.setFont(room_font)
            name = "Pokój*" if room["id"] == "room" and not self.room else room["name"]
            p.save()
            p.setClipRect(title_rect)
            p.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, round(title_rect.width())))
            p.restore()
            if not any(c["room"] == room["id"] for c in self.sim.components.values()):
                p.setPen(QColor("#a29e98"))
                empty_font = QFont("Segoe UI")
                empty_font.setPixelSize(round(max(17, 9 / scale)))
                p.setFont(empty_font)
                p.drawText(rect.adjusted(12, 40, -12, -12), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, "Brak urządzeń w profilu")
        for cid, rect in areas.items():
            component = self.sim.components[cid]
            online = self.sim.nodes[component["node"]]
            color = COLORS[component["kind"]] if online else "#dc8b8b"
            state = self.state_text(cid)
            if (component["kind"] == "gas" and online
                    and self.sim.sensors[cid]["value"] > self.sim.profile["threshold"]):
                color = "#e0af73"
            selected = cid == self.current
            surface = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            surface.setColorAt(0, QColor("#38322d" if selected else "#2b2e33"))
            surface.setColorAt(1, QColor("#24211f" if selected else "#1e2126"))
            p.setBrush(surface)
            p.setPen(QPen(QColor("#d3a580" if selected else "#45484f"), 2 if selected else 1))
            p.drawRoundedRect(rect, 5, 5)
            p.setPen(QPen(QColor(color), 3))
            p.drawLine(rect.topLeft() + QPointF(5, 9), rect.topLeft() + QPointF(5, min(rect.height() - 9, 24)))
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
                text_rect = rect.adjusted(10, 2, -3, -2)
                overview_font = QFont("Consolas")
                lines = 2 if text_rect.height() * scale >= 16 else 1
                font_size = max(1, min(round(8 / scale), int(text_rect.height() * 0.8 / lines)))
                overview_font.setPixelSize(font_size)
                p.setFont(overview_font)
                while p.fontMetrics().height() * lines > text_rect.height() and font_size > 1:
                    font_size -= 1
                    overview_font.setPixelSize(font_size)
                    p.setFont(overview_font)
                metrics = p.fontMetrics()
                width = max(1, int(text_rect.width()))
                if lines == 2:
                    text = (metrics.elidedText(short, Qt.TextElideMode.ElideRight, width) + "\n"
                            + metrics.elidedText(state, Qt.TextElideMode.ElideRight, width))
                else:
                    text = metrics.elidedText(f"{short} {state}", Qt.TextElideMode.ElideRight, width)
                p.save()
                p.setClipRect(text_rect)
                p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)
                p.restore()
        if not self.room:
            p.setPen(QColor("#a19a91"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(50, 735, 660, 22), Qt.AlignmentFlag.AlignCenter, "FRONT / WJAZD    ·    * przypisanie pokoju do potwierdzenia")
