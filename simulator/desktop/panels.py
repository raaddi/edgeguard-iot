"""Reusable configuration and data panels for the desktop laboratory."""

import argparse
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout,
    QHeaderView, QLineEdit, QMessageBox, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)
from simulator.__main__ import identifier


class RunDialog(QDialog):
    def __init__(self, sim, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nowy eksperyment")
        layout, form = QVBoxLayout(self), QFormLayout()
        self.run_id = QLineEdit(f"{sim.run_id[:56]}-new")
        self.run_id.setMaxLength(64)
        self.seed, self.nodes, self.extra = QSpinBox(), QSpinBox(), QSpinBox()
        for widget, maximum, value in [(self.seed, 2**31 - 1, sim.seed), (self.nodes, 3, sim.node_count), (self.extra, 9, sim.extra_nodes)]:
            widget.setRange(1 if widget is self.nodes else 0, maximum)
            widget.setValue(value)
        for label, widget in [("Identyfikator", self.run_id), ("Seed", self.seed), ("Węzły makiety", self.nodes), ("Dodatkowe wirtualne", self.extra)]:
            form.addRow(label, widget)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        try:
            identifier(self.run_id.text())
        except argparse.ArgumentTypeError:
            QMessageBox.warning(self, "Identyfikator", "Użyj 1–64 liter bez polskich znaków, cyfr, _ lub -.")
            return
        super().accept()


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setAlternatingRowColors(True)
    widget.verticalHeader().hide()
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return widget


def fill_table(widget, rows):
    widget.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = widget.item(r, c)
            if item is None:
                item = QTableWidgetItem()
                widget.setItem(r, c, item)
            item.setText(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
