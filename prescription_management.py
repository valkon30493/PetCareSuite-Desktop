# prescription_management.py

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import inventory
from db import connect as _connect


# â â  Ensure the dispensed columns exist â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
def _ensure_dispensed_columns():
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "ALTER TABLE prescriptions ADD COLUMN dispensed INTEGER NOT NULL DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE prescriptions ADD COLUMN date_dispensed TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


_ensure_dispensed_columns()


# â â  CRUD API â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
def get_all_prescriptions():
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 
          pr.prescription_id,
          p.name        AS patient_name,
          pr.medication,
          pr.dosage,
          pr.instructions,
          pr.date_issued,
          pr.dispensed
        FROM prescriptions pr
        JOIN patients p ON pr.patient_id = p.patient_id
        ORDER BY pr.date_issued DESC
    """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def create_prescription(patient_id, medication, dosage, instructions):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO prescriptions
          (patient_id, medication, dosage, instructions, date_issued)
        VALUES (?, ?, ?, ?, datetime('now'))
    """,
        (patient_id, medication, dosage, instructions),
    )
    conn.commit()
    conn.close()


def update_prescription(prescription_id, **fields):
    cols, vals = zip(*fields.items())
    set_clause = ", ".join(f"{col}=?" for col in cols)
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE prescriptions
           SET {set_clause}
         WHERE prescription_id=?
    """,
        (*vals, prescription_id),
    )
    conn.commit()
    conn.close()


def delete_prescription(prescription_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM prescriptions WHERE prescription_id=?", (prescription_id,))
    conn.commit()
    conn.close()


# â â  GUI â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
class PrescriptionManagementScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Prescription Management")
        self.selected_prescription_id = None

        main = QVBoxLayout(self)

        # â â  Table â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Patient",
                "Medication",
                "Dosage",
                "Instructions",
                "Issued",
                "Dispensed?",
            ]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.on_select)
        main.addWidget(self.table)

        # â â  Form â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        form = QFormLayout()
        self.patient_combo = QComboBox()
        self._load_patient_list()
        self.med_input = QLineEdit()
        self.dosage_input = QLineEdit()
        self.instr_input = QPlainTextEdit()
        form.addRow("Patient:", self.patient_combo)
        form.addRow("Medication:", self.med_input)
        form.addRow("Dosage:", self.dosage_input)
        form.addRow("Instructions:", self.instr_input)
        main.addLayout(form)

        # â â  Buttons â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        btns = QHBoxLayout()
        self.new_btn = QPushButton("New")
        self.save_btn = QPushButton("Save")
        self.delete_btn = QPushButton("Delete")
        self.dispense_btn = QPushButton("Dispense")
        for b in (self.new_btn, self.save_btn, self.delete_btn, self.dispense_btn):
            btns.addWidget(b)
        main.addLayout(btns)

        # â â  Connect â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        self.new_btn.clicked.connect(self.on_new)
        self.save_btn.clicked.connect(self.on_save)
        self.delete_btn.clicked.connect(self.on_delete)
        self.dispense_btn.clicked.connect(self.on_dispense)

        self.dispense_btn.setEnabled(False)
        self.refresh()

    def _load_patient_list(self):
        self.patient_combo.clear()
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT patient_id, name FROM patients ORDER BY name")
        for pid, name in cur.fetchall():
            self.patient_combo.addItem(f"{name} (ID:{pid})", pid)
        conn.close()

    def refresh(self):
        self.table.setRowCount(0)
        for pres in get_all_prescriptions():
            r = self.table.rowCount()
            self.table.insertRow(r)
            # pres is (id, patient_name, med, dosage, instr, date_issued, dispensed)
            for c, v in enumerate(pres):
                if c == 6:
                    chk = "âœâ€" if v else ""
                    self.table.setItem(r, c, QTableWidgetItem(chk))
                else:
                    self.table.setItem(r, c, QTableWidgetItem(str(v)))
        self.on_new()  # clear form

    def on_select(self):
        r = self.table.currentRow()
        if r < 0:
            return
        pres_id = int(self.table.item(r, 0).text())
        self.selected_prescription_id = pres_id

        # Pull full record from DB
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT patient_id, medication, dosage, instructions, dispensed
              FROM prescriptions
             WHERE prescription_id = ?
        """,
            (pres_id,),
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            return

        pid, med, dosage, instr, dispensed = row
        idx = self.patient_combo.findData(pid)
        if idx >= 0:
            self.patient_combo.setCurrentIndex(idx)
        self.med_input.setText(med)
        self.dosage_input.setText(dosage)
        self.instr_input.setPlainText(instr)
        self.dispense_btn.setEnabled(not dispensed)

    def on_new(self):
        self.selected_prescription_id = None
        self.patient_combo.setCurrentIndex(0)
        self.med_input.clear()
        self.dosage_input.clear()
        self.instr_input.clear()
        self.dispense_btn.setEnabled(False)

    def on_save(self):
        med = self.med_input.text().strip()
        dosage = self.dosage_input.text().strip()
        instr = self.instr_input.toPlainText().strip()
        pid = self.patient_combo.currentData()
        if not med or not dosage:
            QMessageBox.warning(self, "Input Error", "Medication and dosage required.")
            return

        if self.selected_prescription_id:
            update_prescription(
                self.selected_prescription_id,
                patient_id=pid,
                medication=med,
                dosage=dosage,
                instructions=instr,
            )
        else:
            create_prescription(pid, med, dosage, instr)

        self.refresh()

    def on_delete(self):
        if not self.selected_prescription_id:
            return
        if (
            QMessageBox.question(self, "Confirm", "Delete this prescription?")
            != QMessageBox.Yes
        ):
            return
        delete_prescription(self.selected_prescription_id)
        self.refresh()

    def on_dispense(self):
        """Deduct one unit of the medication from stock and mark dispensed."""
        pid = self.selected_prescription_id
        if not pid:
            return

        # 1) Get medication name
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT medication FROM prescriptions WHERE prescription_id = ?", (pid,)
        )
        res = cur.fetchone()
        conn.close()
        if not res:
            QMessageBox.warning(self, "Error", "Couldn't find that prescription.")
            return
        med_name = res[0]

        # 2) Lookup SKU
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT item_id FROM items WHERE name = ?", (med_name,))
        row = cur.fetchone()
        conn.close()
        if not row:
            QMessageBox.warning(
                self, "No SKU", f"No inventory item named {med_name}found."
            )
            return
        item_id = row[0]

        # 3) Deduct stock
        try:
            inventory.adjust_stock(item_id, -1, f"Dispensed Rx #{pid}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not adjust stock:\n{e}")
            return

        # 4) Mark dispensed
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE prescriptions
               SET dispensed = 1,
                   date_dispensed = datetime('now')
             WHERE prescription_id = ?
        """,
            (pid,),
        )
        conn.commit()
        conn.close()

        QMessageBox.information(
            self, "Dispensed", f"1 × {med_name} removed from stock."
        )
        self.dispense_btn.setEnabled(False)
        # Refresh the little checkmark in the table:
        self.refresh()
