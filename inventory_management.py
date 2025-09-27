# inventory_management.py

import sqlite3, csv
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTableWidget, QTableWidgetItem, QLineEdit, QPlainTextEdit,
    QDoubleSpinBox, QSpinBox, QPushButton, QMessageBox,
    QFileDialog, QInputDialog
)
from PySide6.QtCore import Qt
import inventory  # your existing inventory.py

class InventoryManagementScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Inventory Management")
        self.selected_item_id = None

        main = QVBoxLayout(self)

        # â â  Table â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "ID","Name","Description","Cost","Price","On-Hand","Reorder Lvl"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.on_select)
        main.addWidget(self.table)

        # â â  Form â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        form = QFormLayout()
        self.name_in   = QLineEdit()
        self.desc_in   = QPlainTextEdit()
        self.cost_in   = QDoubleSpinBox(); self.cost_in.setMinimum(0)
        self.price_in  = QDoubleSpinBox(); self.price_in.setMinimum(0)
        self.thresh_in = QSpinBox(); self.thresh_in.setMinimum(0)
        form.addRow("Name:", self.name_in)
        form.addRow("Description:", self.desc_in)
        form.addRow("Unit Cost:", self.cost_in)
        form.addRow("Unit Price:", self.price_in)
        form.addRow("Reorder Threshold:", self.thresh_in)
        main.addLayout(form)

        # â â  Buttons â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        btns = QHBoxLayout()
        self.new_btn    = QPushButton("New")
        self.save_btn   = QPushButton("Save")
        self.delete_btn = QPushButton("Delete")
        self.adjust_btn = QPushButton("Adjust Stock")
        self.export_btn = QPushButton("Export Reorder Report")
        for b in (self.new_btn, self.save_btn, self.delete_btn, self.adjust_btn, self.export_btn):
            btns.addWidget(b)
        main.addLayout(btns)

        # â â  Signals â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        self.new_btn.clicked.connect(self.on_new)
        self.save_btn.clicked.connect(self.on_save)
        self.delete_btn.clicked.connect(self.on_delete)
        self.adjust_btn.clicked.connect(self.on_adjust)
        self.export_btn.clicked.connect(self.on_export)

        self.refresh()
        self.check_low_stock_and_alert()

    def refresh(self):
        self.table.setRowCount(0)
        for row in inventory.get_all_items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(str(v)))

    def on_select(self):
        r = self.table.currentRow()
        if r < 0:
            return
        self.selected_item_id = int(self.table.item(r, 0).text())
        self.name_in.setText(self.table.item(r, 1).text())
        self.desc_in.setPlainText(self.table.item(r, 2).text())
        self.cost_in.setValue(float(self.table.item(r, 3).text()))
        self.price_in.setValue(float(self.table.item(r, 4).text()))
        self.thresh_in.setValue(int(self.table.item(r, 6).text()))

    def on_new(self):
        self.selected_item_id = None
        self.name_in.clear()
        self.desc_in.clear()
        self.cost_in.setValue(0)
        self.price_in.setValue(0)
        self.thresh_in.setValue(0)

    def on_save(self):
        name = self.name_in.text().strip()
        if not name:
            QMessageBox.warning(self, "Input Error", "Name is required.")
            return
        desc = self.desc_in.toPlainText()
        cost, price, thr = self.cost_in.value(), self.price_in.value(), self.thresh_in.value()
        if self.selected_item_id:
            inventory.update_item(
                self.selected_item_id,
                name=name, description=desc,
                unit_cost=cost, unit_price=price,
                reorder_threshold=thr
            )
        else:
            inventory.create_item(name, desc, cost, price, thr)
        self.refresh()
        self.on_select()
        self.on_new()

    def on_delete(self):
        if not self.selected_item_id:
            return
        if QMessageBox.question(self, "Confirm", "Delete this item?") != QMessageBox.Yes:
            return
        inventory.delete_item(self.selected_item_id)
        self.on_new()
        self.refresh()
        self.on_select()

    def on_adjust(self):
        if not self.selected_item_id:
            return
        qty, ok = QInputDialog.getInt(self, "Adjust Stock", "Άqty (+/-):", 0)
        if not ok:
            return
        reason, ok = QInputDialog.getText(self, "Reason", "Reason for adjustment:")
        if not ok:
            reason = None
        inventory.adjust_stock(self.selected_item_id, qty, reason)
        self.refresh()
        self.on_select()
        self.check_low_stock_and_alert()

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "reorder_report.csv", "*.csv")
        if not path:
            return
        rows = inventory.items_below_reorder()
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ID","Name","Desc","Cost","Price","Threshold","OnHand"])
            w.writerows(rows)
        QMessageBox.information(self, "Exported", f"Saved to {path}")

    def check_low_stock_and_alert(self):
        low = inventory.items_below_reorder()
        if not low:
            return
        # Build a friendly HTML list
        lines = [f"{row[1]} (On-Hand: {row[5]}, Reorder @ {row[6]})" for row in low]
        QMessageBox.warning(
            self,
            "Low Stock Warning",
            "<b>The following items are at or below reorder level:</b><br>" +
            "<br>".join(lines)
        )
