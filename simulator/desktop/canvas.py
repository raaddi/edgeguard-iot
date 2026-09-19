"""Telemetry plot; gaps never interpolate a missing device message."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

BG, GRID, TEXT, MUTED, BLUE, GREEN, AMBER = "#030507", "#19212c", "#dce3ec", "#8d9bac", "#75b8fa", "#73d4b5", "#e9bd6a"


class SignalPlot(QWidget):
    def __init__(self, sim, component="gas_01", compact=False, color=GREEN):
        super().__init__()
        self.sim = sim
        self.component, self.compact, self.color = component, compact, color
        self.setMinimumSize(220 if compact else 400, 180 if compact else 160)
        self.setAccessibleName(f"Telemetria {component}")

    @property
    def kind(self):
        return self.sim.components[self.component]["kind"]

    @property
    def scale(self):
        return 180 if self.kind == "servo" else 1

    def samples(self, field="reported"):
        node = self.sim.components[self.component]["node"]
        section, key = ("sensors", "value") if self.kind == "gas" else ("actuators", field)
        recent = {m["sequence_number"]: m[section].get(self.component, {}).get(key)
                  for m in self.sim.history if m["device_id"] == node}
        return [(tick, recent.get(tick)) for tick in range(max(0, self.sim.time - 120), self.sim.time)]

    def status_text(self):
        node = self.sim.components[self.component]["node"]
        if not self.sim.nodes[node]:
            return "OFFLINE · brak nowej próbki"
        value = self.samples()[-1][1]
        if self.kind == "gas":
            return "brak próbki" if value is None else f"{value:.3f} / 0–1 · t={self.sim.time - 1} s"
        commanded = self.samples("commanded")[-1][1]
        def fmt(number):
            if number is None:
                return "—"
            return f"{number}°" if self.kind == "servo" else "ON" if number else "OFF"
        return f"Zadane: {fmt(commanded)} · raport: {fmt(value)}"

    @staticmethod
    def trace(samples, box, first, last, scale, stepped=False):
        path, previous = QPainterPath(), None
        points = []
        for tick, value in samples:
            if value is None:
                previous = None
                continue
            point = QPointF(box.left() + (tick - first) / (last - first) * box.width(),
                            box.bottom() - value / scale * box.height())
            if previous is None:
                path.moveTo(point)
            else:
                if stepped:
                    path.lineTo(QPointF(point.x(), previous.y()))
                path.lineTo(point)
            previous = point
            points.append(point)
        return path, points

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        box = QRectF(40, 54, self.width() - 55, self.height() - 83)
        samples = self.samples()
        first, last = samples[0][0], max(samples[0][0] + 10, samples[-1][0])
        p.setFont(QFont("Segoe UI", 9 if self.compact else 10))
        p.setPen(QColor(self.color))
        name = self.sim.components[self.component]["name"]
        title = f"{self.component} · {name}"
        p.drawText(10, 17, p.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, self.width() - 20))
        node = self.sim.components[self.component]["node"]
        online = self.sim.nodes[node]
        p.setPen(QColor(MUTED if online else "#ff657a"))
        p.drawText(10, 35, self.status_text())
        p.setFont(QFont("Consolas", 9 if self.compact else 10))
        ticks = (0, 90, 180) if self.kind == "servo" else (0, 0.5, 1) if self.kind == "gas" else (0, 1)
        for value in ticks:
            y = box.bottom() - value / self.scale * box.height()
            p.setPen(QPen(QColor(GRID), 1))
            p.drawLine(QPointF(box.left(), y), QPointF(box.right(), y))
            p.setPen(QColor(MUTED))
            label = f"{value}°" if self.kind == "servo" else f"{value:.1f}" if self.kind == "gas" else "ON" if value else "OFF"
            p.drawText(QPointF(4, y + 4), label)
        p.drawText(QPointF(box.left(), box.bottom() + 23), str(first))
        p.drawText(QPointF(box.right() - 60, box.bottom() + 23), f"{last} s")
        if self.kind == "gas":
            threshold_y = box.bottom() - self.sim.profile["threshold"] * box.height()
            p.setPen(QPen(QColor(AMBER), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(box.left(), threshold_y), QPointF(box.right(), threshold_y))
        else:
            command_path, command_points = self.trace(self.samples("commanded"), box, first, last, self.scale, True)
            p.setPen(QPen(QColor(AMBER), 4, Qt.PenStyle.DashLine))
            p.drawPath(command_path)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for point in command_points:
                p.drawEllipse(point, 3, 3)
        path, points = self.trace(samples, box, first, last, self.scale, self.kind != "gas")
        p.setPen(QPen(QColor(self.color), 2))
        p.drawPath(path)
        p.setBrush(QColor(self.color))
        for point in points:
            p.drawEllipse(point, 2, 2)


class SignalGrid(QScrollArea):
    """All components, grouped by kind; reported values are never model shortcuts."""

    GROUPS = [("gas", "Czujniki gazu", "#49d7ff"), ("fan", "Wentylatory", "#5cedab"),
              ("light", "Oświetlenie", "#ffd366"), ("servo", "Serwa / bramy i drzwi", "#b795ff")]

    def __init__(self, sim):
        super().__init__()
        self.setWidgetResizable(True)
        self.setMinimumHeight(190)
        self.setAccessibleName("Wykresy wszystkich urządzeń całej makiety")
        self.kind_filter = None
        self.set_simulation(sim)

    def set_simulation(self, sim):
        previous = self.takeWidget()
        if previous is not None:
            previous.deleteLater()
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)
        self.plots = {}
        self.groups = {}
        for kind, title, color in self.GROUPS:
            members = [cid for cid, component in sim.components.items() if component["kind"] == kind]
            group = QWidget()
            grid = QGridLayout(group)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(6)
            heading = QLabel(f"{title.upper()}  /  {len(members)}")
            heading.setStyleSheet(f"color: {color}; font-weight: 600")
            grid.addWidget(heading, 0, 0, 1, 4)
            for index, cid in enumerate(members):
                plot = SignalPlot(sim, cid, compact=True, color=color)
                plot.setToolTip(f"{sim.components[cid]['name']} / {sim.components[cid]['node']}\n"
                               + ("Gaz 0–1, nie ppm. Linia przerywana: próg."
                                  if kind == "gas" else "Linia przerywana: zadane; ciągła: raportowane.\n"
                                  "W tej makiecie raport pochodzi z symulacji, nie pomiaru sprzętu."))
                self.plots[cid] = plot
                grid.addWidget(plot, 1 + index // 4, index % 4)
            for column in range(4):
                grid.setColumnStretch(column, 1)
            self.groups[kind] = group
            layout.addWidget(group)
        layout.addStretch()
        self.setWidget(panel)
        self.set_kind(self.kind_filter)

    def set_kind(self, kind):
        self.kind_filter = kind
        for key, group in self.groups.items():
            group.setVisible(kind is None or key == kind)
        self.verticalScrollBar().setValue(0)

    def refresh(self):
        for plot in self.plots.values():
            plot.update()
