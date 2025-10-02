# billing_invoicing.py
# -----------------------------------------------------------------------------
# PetWellnessApp â€â€ Billing & Invoicing (DB unified)
# All SQLite access goes through _connect() using backup.DB_PATH
# Uses backup.LOGO_PNG for logo in PDFs (works in dev & PyInstaller builds)
# -----------------------------------------------------------------------------
import sys
import os
import csv
import tempfile
from datetime import datetime
from db import connect as _connect

import win32print
from PySide6 import QtGui
from PySide6.QtCore import QDate, QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QLineEdit, QComboBox, QFormLayout, QHeaderView, QFileDialog,
    QMessageBox, QSpinBox, QDialog, QDoubleSpinBox, QDateTimeEdit, QDateEdit,
    QSizePolicy, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QLineEdit, QLabel
)
from PySide6.QtPrintSupport import QPrinterInfo

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm

from logger import log_error
from backup import LOGO_PNG
from backup import DB_PATH

# Small helpers / styling
BTN_STYLE = """
QPushButton {
  font-size: 14px;
  padding: 8px 16px;
  min-height: 40px;
}
"""



def _find_logo_path():
    """
    Resolve the clinic logo path.
    1) If backup.LOGO_PNG exists, use it.
    2) Else try common locations (handles dev & PyInstaller).
    """
    try:
        if LOGO_PNG and os.path.exists(str(LOGO_PNG)):
            return str(LOGO_PNG)
    except Exception:
        pass

    # Fallback scan (should rarely be needed if LOGO_PNG is bundled)
    env = os.getenv("PETWELLNESS_LOGO")
    if env and os.path.exists(env):
        return env

    names = [
        "pet_wellness_logo.png", "pet_wellness_logo.jpg",
        "clinic_logo.png", "clinic_logo.jpg",
        "logo.png", "logo.jpg",
    ]
    bases = []
    if hasattr(sys, "_MEIPASS"):
        bases.append(sys._MEIPASS)
    bases.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    bases.append(os.path.dirname(__file__))
    bases.append(os.getcwd())
    bases.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    candidates = []
    for base in bases:
        for n in names:
            candidates.append(os.path.join(base, n))
            candidates.append(os.path.join(base, "assets", n))
            candidates.append(os.path.join(base, "resources", n))

    try:
        db_dir = os.path.dirname(str(DB_PATH))
        for n in names:
            candidates.append(os.path.join(db_dir, n))
            candidates.append(os.path.join(db_dir, "assets", n))
    except Exception:
        pass

    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


# Dialogs
class PaymentHistoryDialog(QDialog):
    def __init__(self, invoice_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Payment History")
        self.invoice_id = invoice_id

        layout = QVBoxLayout(self)

        self.payment_table = QTableWidget()
        self.payment_table.setColumnCount(4)
        self.payment_table.setHorizontalHeaderLabels(["Payment\nDate", "Amount\nPaid", "Payment\nMethod", "Notes"])
        self.payment_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.payment_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.payment_table.horizontalHeader().setStyleSheet("QHeaderView::section { padding:6px; height:44px; }")
        self.payment_table.setWordWrap(True)
        layout.addWidget(self.payment_table)

        self.load_payment_history()

    def load_payment_history(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT payment_date, amount_paid, payment_method, notes
              FROM payment_history
             WHERE invoice_id = ?
             ORDER BY datetime(payment_date) ASC
            """,
            (self.invoice_id,),
        )
        payments = cur.fetchall()
        conn.close()

        self.payment_table.setRowCount(0)
        for r, row in enumerate(payments):
            self.payment_table.insertRow(r)
            for c, val in enumerate(row):
                self.payment_table.setItem(r, c, QTableWidgetItem(str(val)))


class AddPaymentDialog(QDialog):
    def __init__(self, invoice_id, remaining_balance, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Payment")
        self.invoice_id = invoice_id
        self.remaining_balance = remaining_balance

        layout = QVBoxLayout()
        form_layout = QFormLayout()

        # Amount
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("Enter Payment Amount")
        form_layout.addRow("Amount Paid:", self.amount_input)

        # Method
        self.payment_method_dropdown = QComboBox()
        self.payment_method_dropdown.addItems(["Cash", "Card", "Bank Transfer", "Online Payment", "Other"])
        form_layout.addRow("Payment Method:", self.payment_method_dropdown)

        # Date/Time
        self.payment_dt = QDateTimeEdit(QDateTime.currentDateTime())
        self.payment_dt.setCalendarPopup(True)
        self.payment_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        form_layout.addRow("Payment Date/Time:", self.payment_dt)

        # Notes
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Optional Notes")
        form_layout.addRow("Notes:", self.notes_input)

        layout.addLayout(form_layout)

        save_button = QPushButton("Save Payment")
        save_button.clicked.connect(self.save_payment)
        layout.addWidget(save_button)

        self.setLayout(layout)

    def save_payment(self):
        try:
            amount_paid = float(self.amount_input.text().strip())
            if amount_paid <= 0:
                raise ValueError("Payment amount must be greater than zero.")
            if amount_paid > self.remaining_balance:
                raise ValueError("Payment amount exceeds remaining balance.")

            payment_method = self.payment_method_dropdown.currentText()
            notes = self.notes_input.text().strip()
            pay_dt_str = self.payment_dt.dateTime().toString("yyyy-MM-dd HH:mm:ss")

            if self.payment_dt.dateTime() > QDateTime.currentDateTime().addSecs(60):
                raise ValueError("Payment date cannot be in the future.")

            conn = _connect()
            cursor = conn.cursor()

            cursor.execute(
                '''
                INSERT INTO payment_history (invoice_id, payment_date, amount_paid, payment_method, notes)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (self.invoice_id, pay_dt_str, amount_paid, payment_method, notes),
            )

            cursor.execute(
                '''
                UPDATE invoices
                   SET payment_status = CASE
                         WHEN (SELECT COALESCE(SUM(amount_paid),0)
                                 FROM payment_history WHERE invoice_id = ?) >= final_amount THEN 'Paid'
                         ELSE 'Partially Paid'
                       END,
                       payment_method = ?
                 WHERE invoice_id = ?
                ''',
                (self.invoice_id, payment_method, self.invoice_id),
            )

            conn.commit()
            conn.close()

            QMessageBox.information(self, "Success", "Payment added successfully.")
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Input Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")


class AppointmentPickerDialog(QDialog):
    """Pick an appointment by Owner name and date range to fill Appointment ID."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Find Appointment (by Owner)")
        self.selected_id = None

        root = QVBoxLayout(self)

        form = QHBoxLayout()
        # RENAMED: owner_search (was pet_search)
        self.owner_search = QLineEdit()
        self.owner_search.setPlaceholderText("Owner name contains…")
        form.addWidget(QLabel("Owner:"))
        form.addWidget(self.owner_search)

        self.start_date = QDateEdit(QDate.currentDate().addMonths(-3))
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date = QDateEdit(QDate.currentDate().addDays(1))
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")

        form.addWidget(QLabel("From:"))
        form.addWidget(self.start_date)
        form.addWidget(QLabel("To:"))
        form.addWidget(self.end_date)

        search_btn = QPushButton("Search")
        search_btn.setStyleSheet(BTN_STYLE)
        search_btn.clicked.connect(self._do_search)
        form.addWidget(search_btn)
        root.addLayout(form)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        # Columns unchanged: ID | Date/Time | Pet | Owner
        self.table.setHorizontalHeaderLabels(["Appointment\nID", "Date/\nTime", "Pet", "Owner"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStyleSheet("QHeaderView::section { padding:6px; height:44px; }")
        self.table.setWordWrap(True)
        self.table.itemDoubleClicked.connect(self._accept_current)
        root.addWidget(self.table)

        btns = QHBoxLayout()
        use_btn = QPushButton("Use Appointment")
        use_btn.setStyleSheet(BTN_STYLE)
        use_btn.clicked.connect(self._accept_current)
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(BTN_STYLE)
        cancel.clicked.connect(self.reject)
        btns.addWidget(use_btn)
        btns.addWidget(cancel)
        root.addLayout(btns)

    def _do_search(self):
        owner_like = f"%{(self.owner_search.text() or '').strip()}%"
        s = self.start_date.date().toString("yyyy-MM-dd")
        e = self.end_date.date().toString("yyyy-MM-dd")
        conn = _connect()
        cur = conn.cursor()
        # CHANGED: search by OWNER ONLY
        cur.execute(
            """
            SELECT a.appointment_id, a.date_time, p.name AS pet_name, p.owner_name
              FROM appointments a
              JOIN patients p ON a.patient_id = p.patient_id
             WHERE p.owner_name LIKE ?
               AND date(a.date_time) BETWEEN date(?) AND date(?)
             ORDER BY a.date_time DESC
            """,
            (owner_like, s, e),
        )
        rows = cur.fetchall()
        conn.close()

        self.table.setRowCount(0)
        for r, row in enumerate(rows):
            self.table.insertRow(r)
            for c, val in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(str(val)))

    def _accept_current(self):
        r = self.table.currentRow()
        if r < 0:
            QMessageBox.warning(self, "No Selection", "Please select an appointment.")
            return
        self.selected_id = int(self.table.item(r, 0).text())
        self.accept()

    def get_selected_id(self):
        return self.selected_id



class ItemizedBillingDialog(QDialog):
    """
    Add/Edit a single invoice item with TOTAL (incl VAT) as primary input.
    Audit math:
      base_before_disc = unit_net * qty
      net_after_disc = base_before_disc * (1 - d)
      vat_amount = net_after_disc * r
      total_gross = net_after_disc * (1 + r)
      discount_amount = base_before_disc - net_after_disc
    We solve backwards from total_gross to get unit_net.
    """

    def __init__(self, invoice_id, item_id=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Invoice Item")
        self.invoice_id = invoice_id
        self.item_id = item_id

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.description_input = QLineEdit()
        form.addRow("Description:", self.description_input)

        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 1000)
        self.quantity_input.valueChanged.connect(self._recalc_from_total)
        form.addRow("Quantity:", self.quantity_input)

        self.vat_pct_input = QComboBox()
        self.vat_pct_input.addItems(["0", "5", "19"])
        self.vat_pct_input.currentIndexChanged.connect(self._recalc_from_total)
        form.addRow("VAT Rate (%):", self.vat_pct_input)

        self.discount_pct_input = QSpinBox()
        self.discount_pct_input.setRange(0, 100)
        self.discount_pct_input.setSuffix(" %")
        self.discount_pct_input.valueChanged.connect(self._recalc_from_total)
        form.addRow("Item Discount (%):", self.discount_pct_input)

        self.total_gross_input = QDoubleSpinBox()
        self.total_gross_input.setRange(0.01, 1000000.00)
        self.total_gross_input.setDecimals(2)
        self.total_gross_input.valueChanged.connect(self._recalc_from_total)
        form.addRow("Total (incl. VAT) (€):", self.total_gross_input)

        # Derived, read-only:
        self.unit_net_show = QLineEdit("0.00")
        self.unit_net_show.setReadOnly(True)
        form.addRow("Unit (net) (€):", self.unit_net_show)

        self.vat_amount_show = QLineEdit("0.00")
        self.vat_amount_show.setReadOnly(True)
        form.addRow("VAT Amount (€):", self.vat_amount_show)

        self.discount_amount_show = QLineEdit("0.00")
        self.discount_amount_show.setReadOnly(True)
        form.addRow("Discount (€):", self.discount_amount_show)

        layout.addLayout(form)

        save_btn = QPushButton("Save Item")
        save_btn.setStyleSheet(BTN_STYLE)
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        if self.item_id:
            self._load_existing()

    def _recalc_from_total(self):
        qty = max(1, int(self.quantity_input.value()))
        r = float(self.vat_pct_input.currentText()) / 100.0
        d = self.discount_pct_input.value() / 100.0
        T = float(self.total_gross_input.value() or 0.0)

        if T <= 0:
            self.unit_net_show.setText("0.00")
            self.vat_amount_show.setText("0.00")
            self.discount_amount_show.setText("0.00")
            return

        net_after_disc = T / (1.0 + r)
        base_before_disc = net_after_disc / max(1e-9, (1.0 - d))
        unit_net = base_before_disc / qty
        discount_amount = base_before_disc - net_after_disc
        vat_amount = T - net_after_disc

        self.unit_net_show.setText(f"{unit_net:.4f}")
        self.vat_amount_show.setText(f"{vat_amount:.2f}")
        self.discount_amount_show.setText(f"{discount_amount:.2f}")

    def _load_existing(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT description, quantity, unit_price, vat_pct, vat_amount,
                   discount_pct, discount_amount, total_price
              FROM invoice_items
             WHERE item_id = ?
            """,
            (self.item_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return
        (
            desc,
            qty,
            unit_net,
            vat_frac,
            vat_amt,
            disc_frac,
            disc_amt,
            total_gross,
        ) = row

        self.description_input.setText(desc or "")
        self.quantity_input.setValue(int(qty or 1))
        self.vat_pct_input.setCurrentText(str(int(round((vat_frac or 0) * 100))))
        self.discount_pct_input.setValue(int(round((disc_frac or 0) * 100)))
        self.total_gross_input.setValue(float(total_gross or 0))
        self.unit_net_show.setText(f"{float(unit_net or 0):.4f}")
        self.vat_amount_show.setText(f"{float(vat_amt or 0):.2f}")
        self.discount_amount_show.setText(f"{float(disc_amt or 0):.2f}")

    def _save(self):
        desc = self.description_input.text().strip()
        if not desc:
            QMessageBox.warning(self, "Input Error", "Description is required.")
            return

        qty = max(1, int(self.quantity_input.value()))
        r = float(self.vat_pct_input.currentText()) / 100.0
        d = self.discount_pct_input.value() / 100.0
        T = float(self.total_gross_input.value() or 0.0)

        net_after_disc = T / (1.0 + r)
        base_before_disc = net_after_disc / max(1e-9, (1.0 - d))
        unit_net = base_before_disc / qty
        discount_amount = base_before_disc - net_after_disc
        vat_amount = T - net_after_disc

        try:
            conn = _connect()
            cur = conn.cursor()
            if self.item_id:
                cur.execute(
                    """
                    UPDATE invoice_items
                       SET description=?, quantity=?, unit_price=?, vat_pct=?, vat_amount=?,
                           discount_pct=?, discount_amount=?, total_price=?, vat_flag=?
                     WHERE item_id=?
                    """,
                    (
                        desc,
                        qty,
                        unit_net,
                        r,
                        vat_amount,
                        d,
                        discount_amount,
                        T,
                        "B" if int(round(r * 100)) == 5 else "C" if int(round(r * 100)) == 19 else "",
                        self.item_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO invoice_items
                      (invoice_id, description, quantity, unit_price,
                       vat_pct, vat_amount, discount_pct, discount_amount, total_price, vat_flag)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        self.invoice_id,
                        desc,
                        qty,
                        unit_net,
                        r,
                        vat_amount,
                        d,
                        discount_amount,
                        T,
                        "B" if int(round(r * 100)) == 5 else "C" if int(round(r * 100)) == 19 else "",
                    ),
                )
            conn.commit()
            conn.close()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save item: {e}")


class InvoiceReminderDialog(QDialog):
    def __init__(self, invoice_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Set Payment Reminder for Invoice #{invoice_id}")
        self.invoice_id = invoice_id

        layout = QVBoxLayout(self)
        form = QFormLayout()

        dt = QDateTime.currentDateTime().addDays(1)
        self.dt_picker = QDateTimeEdit(dt)
        self.dt_picker.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.dt_picker.setCalendarPopup(True)
        form.addRow("Reminder Time:", self.dt_picker)

        self.reason_input = QLineEdit(f"Invoice #{invoice_id} payment due")
        form.addRow("Reason:", self.reason_input)

        layout.addLayout(form)

        btns = QHBoxLayout()
        ok = QPushButton("Save")
        ok.setStyleSheet(BTN_STYLE)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(BTN_STYLE)
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def get_values(self):
        return (
            self.dt_picker.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            self.reason_input.text().strip(),
        )

# --- OwnerPicker dialog (new) ---
class OwnerPicker(QDialog):
    """Pick an owner for walk‑in sales; optional free‑text contact/email.
    Pulls unique owners from `patients` table to reduce typos.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Owner")
        lay = QVBoxLayout(self)
        form = QFormLayout()

        # Distinct owners from patients
        self.owner_combo = QComboBox()
        self.owner_combo.setEditable(True)  # allow typing new names too
        owners = self._load_owners()
        self.owner_combo.addItems(owners)
        form.addRow("Owner:", self.owner_combo)

        self.contact_in = QLineEdit()
        form.addRow("Owner Contact:", self.contact_in)

        self.email_in = QLineEdit()
        form.addRow("Owner Email:", self.email_in)

        lay.addLayout(form)

        buttons = QHBoxLayout()
        ok = QPushButton("Continue"); ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        buttons.addWidget(ok); buttons.addWidget(cancel)
        lay.addLayout(buttons)

    def _load_owners(self) -> list[str]:
        try:
            conn = _connect(); cur = conn.cursor()
            cur.execute("""
                SELECT DISTINCT owner_name
                  FROM patients
                 WHERE owner_name IS NOT NULL AND TRIM(owner_name) <> ''
                 ORDER BY owner_name
            """)
            rows = [r[0] for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def get_values(self):
        return (
            self.owner_combo.currentText().strip(),
            self.contact_in.text().strip(),
            self.email_in.text().strip(),
        )

# Main Screen
class BillingInvoicingScreen(QWidget):
    invoiceSelected = Signal(int)  # emits invoice_id

    def __init__(self):
        super().__init__()
        self.selected_invoice_id = None
        self.invoices = []
        self._opened_from_appointments = False

        root = QHBoxLayout(self)

        # LEFT: filters + invoice list
        left = QVBoxLayout()
        filters = QHBoxLayout()
        self.search_input = QLineEdit()
        # CHANGED: mention Owner in placeholder
        self.search_input.setPlaceholderText("Search by Patient/Owner or Appt ID…")
        self.search_input.textChanged.connect(self.apply_filters)
        filters.addWidget(self.search_input)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Open", "Paid"])
        self.status_filter.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(self.status_filter)
        left.addLayout(filters)

        dates = QHBoxLayout()
        self.start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.dateChanged.connect(self.apply_filters)
        self.end_date = QDateEdit(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.dateChanged.connect(self.apply_filters)
        dates.addWidget(QLabel("From:"))
        dates.addWidget(self.start_date)
        dates.addWidget(QLabel("To:"))
        dates.addWidget(self.end_date)
        left.addLayout(dates)

        self.invoice_table = QTableWidget()
        self.invoice_table.setColumnCount(9)
        # CHANGED: column 3 name reflects patient OR owner
        self.invoice_table.setHorizontalHeaderLabels(
            [
                "Invoice\nID",
                "Appointment\nID",
                "Patient/Owner\nName",
                "Total\nAmount",
                "Final\nAmount",
                "Payment\nStatus",
                "Payment\nMethod",
                "Remaining\nBalance",
                "Created\nAt",
            ]
        )
        self.invoice_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.invoice_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.invoice_table.horizontalHeader().setStyleSheet("QHeaderView::section { padding:6px; height:44px; }")
        self.invoice_table.setWordWrap(True)
        self.invoice_table.itemSelectionChanged.connect(self.load_selected_invoice)
        self.invoice_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left.addWidget(self.invoice_table)

        strip = QHBoxLayout()
        self.item_count_label = QLabel("Items: 0")
        self.total_amount_label = QLabel("Total: €0.00")
        self.remaining_balance_summary = QLabel("Remaining: €0.00")
        self.payment_count_label = QLabel("Payments: 0")
        for w in (
            self.item_count_label,
            self.total_amount_label,
            self.remaining_balance_summary,
            self.payment_count_label,
        ):
            w.setStyleSheet("font-weight: 600;")
            strip.addWidget(w)
        left.addLayout(strip)

        # CENTER: items + form
        center_widget = QWidget()
        center = QVBoxLayout(center_widget)

        self.item_table = QTableWidget()
        self.item_table.setColumnCount(6)
        self.item_table.setHorizontalHeaderLabels(
            [
                "Description",
                "Quantity",
                "Unit\n(net)",
                "VAT\nAmount",
                "Discount",
                "Total\n(incl. VAT)",
            ]
        )
        self.item_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.item_table.horizontalHeader().setStyleSheet("QHeaderView::section { padding:6px; height:44px; }")
        self.item_table.setWordWrap(True)
        self.item_table.itemSelectionChanged.connect(self._on_item_selection)
        self.item_table.setMinimumHeight(160)
        self.item_table.setMaximumHeight(260)
        center.addWidget(self.item_table)

        item_btns = QHBoxLayout()
        self.add_item_button = QPushButton("Add Item")
        self.add_item_button.setStyleSheet(BTN_STYLE)
        self.add_item_button.setEnabled(False)
        self.add_item_button.clicked.connect(self.add_item)
        self.edit_item_button = QPushButton("Edit Item")
        self.edit_item_button.setStyleSheet(BTN_STYLE)
        self.edit_item_button.setEnabled(False)
        self.edit_item_button.clicked.connect(self.edit_item)
        self.delete_item_button = QPushButton("Delete Item")
        self.delete_item_button.setStyleSheet(BTN_STYLE)
        self.delete_item_button.setEnabled(False)
        self.delete_item_button.clicked.connect(self.delete_item)
        item_btns.addWidget(self.add_item_button)
        item_btns.addWidget(self.edit_item_button)
        item_btns.addWidget(self.delete_item_button)
        center.addLayout(item_btns)

        bottom = QGridLayout()
        ro = "background-color:#f7f7f7;color:#555;"

        bottom.addWidget(QLabel("Appointment ID:"), 0, 0)
        self.appointment_id_input = QLineEdit()
        self.appointment_id_input.setPlaceholderText("Enter Appointment ID or use Find… (optional)")
        self.appointment_id_input.textChanged.connect(self.fetch_patient_details)
        bottom.addWidget(self.appointment_id_input, 0, 1)

        self.find_appt_btn = QPushButton("Find Appointment…")
        self.find_appt_btn.setStyleSheet(BTN_STYLE)
        self.find_appt_btn.clicked.connect(self._find_appointment)
        bottom.addWidget(self.find_appt_btn, 0, 2)

        bottom.addWidget(QLabel("Patient/Owner:"), 1, 0)
        self.patient_name_label = QLineEdit()
        self.patient_name_label.setReadOnly(True)
        self.patient_name_label.setStyleSheet(ro)
        bottom.addWidget(self.patient_name_label, 1, 1, 1, 2)

        # NEW: Owner snapshot (visible only for walk-ins)
        self.owner_snapshot_lbl = QLabel("Owner contact/email:")
        self.owner_snapshot = QLineEdit()
        self.owner_snapshot.setReadOnly(True)
        self.owner_snapshot.setStyleSheet(ro)
        bottom.addWidget(self.owner_snapshot_lbl, 2, 0)
        bottom.addWidget(self.owner_snapshot, 2, 1, 1, 2)

        bottom.addWidget(QLabel("Appointment Date:"), 2, 0)
        self.date_label = QLineEdit()
        self.date_label.setReadOnly(True)
        self.date_label.setStyleSheet(ro)
        bottom.addWidget(self.date_label, 2, 1, 1, 2)

        bottom.addWidget(QLabel("Invoice Discount (%):"), 3, 0)
        self.discount_input = QSpinBox()
        self.discount_input.setRange(0, 100)
        self.discount_input.setSuffix(" %")
        self.discount_input.valueChanged.connect(self.calculate_final_amount)
        bottom.addWidget(self.discount_input, 3, 1)

        bottom.addWidget(QLabel("Subtotal (gross):"), 4, 0)
        self.total_amount_input = QLineEdit()
        self.total_amount_input.setReadOnly(True)
        self.total_amount_input.setStyleSheet(ro)
        bottom.addWidget(self.total_amount_input, 4, 1)

        bottom.addWidget(QLabel("Final Total:"), 5, 0)
        self.final_amount_label = QLineEdit()
        self.final_amount_label.setReadOnly(True)
        self.final_amount_label.setStyleSheet(ro)
        bottom.addWidget(self.final_amount_label, 5, 1)

        bottom.addWidget(QLabel("Remaining Balance:"), 6, 0)
        self.remaining_balance_label = QLineEdit()
        self.remaining_balance_label.setReadOnly(True)
        self.remaining_balance_label.setStyleSheet(ro)
        bottom.addWidget(self.remaining_balance_label, 6, 1)

        bottom.addWidget(QLabel("Payment Status:"), 7, 0)
        self.payment_status_dropdown = QComboBox()
        self.payment_status_dropdown.addItems(["Unpaid", "Partially Paid", "Paid", "N/A"])
        self.payment_status_dropdown.setEnabled(False)
        bottom.addWidget(self.payment_status_dropdown, 7, 1)

        bottom.addWidget(QLabel("Payment Method:"), 8, 0)
        self.payment_method_dropdown = QComboBox()
        self.payment_method_dropdown.addItems(["Cash", "Card", "Bank Transfer", "Online Payment", "Other"])
        self.payment_method_dropdown.setEnabled(False)
        bottom.addWidget(self.payment_method_dropdown, 8, 1)

        center.addLayout(bottom)

        # Owner information hidden until we detect a walk-in
        self._set_owner_snapshot(None, None, show=False)

        center_widget.setMaximumWidth(700)

        # RIGHT: vertical buttons column
        buttons_col = QVBoxLayout()
        buttons_col.setAlignment(Qt.AlignTop)
        buttons_col.addSpacing(80)

        def _stack(b: QPushButton):
            b.setStyleSheet(BTN_STYLE)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setMinimumWidth(180)
            buttons_col.addWidget(b)

        self.new_invoice_btn = QPushButton("New Invoice (from Appt)")
        _stack(self.new_invoice_btn)
        self.new_invoice_btn.clicked.connect(self.create_invoice)

        # NEW: walk-in invoice
        self.walkin_invoice_btn = QPushButton("New Walk-in Invoice")
        _stack(self.walkin_invoice_btn)
        self.walkin_invoice_btn.clicked.connect(self.create_walkin_invoice)

        self.create_estimate_btn = QPushButton("Create Estimate")
        _stack(self.create_estimate_btn)
        self.create_estimate_btn.clicked.connect(self.create_estimate)

        self.create_charity_btn = QPushButton("Create Charity")
        _stack(self.create_charity_btn)
        self.create_charity_btn.clicked.connect(self.create_charity)

        self.save_btn = QPushButton("Save Invoice")
        _stack(self.save_btn)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.edit_invoice)

        self.view_payments_button = QPushButton("View Payments")
        _stack(self.view_payments_button)
        self.view_payments_button.setEnabled(False)
        self.view_payments_button.clicked.connect(self.view_payment_history)

        self.add_payment_button = QPushButton("Add Payment")
        _stack(self.add_payment_button)
        self.add_payment_button.setEnabled(False)
        self.add_payment_button.clicked.connect(self.add_payment)

        self.delete_payment_button = QPushButton("Delete Payment")
        _stack(self.delete_payment_button)
        self.delete_payment_button.setEnabled(False)
        self.delete_payment_button.clicked.connect(self.delete_payment)

        self.send_reminder_button = QPushButton("Send Reminder")
        _stack(self.send_reminder_button)
        self.send_reminder_button.setEnabled(False)
        self.send_reminder_button.clicked.connect(self.send_invoice_reminder)

        self.delete_button = QPushButton("Delete Invoice")
        _stack(self.delete_button)
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_invoice)

        self.print_button = QPushButton("Print / Save PDF")
        _stack(self.print_button)
        self.print_button.setEnabled(False)
        self.print_button.clicked.connect(self.print_invoice)

        self.convert_btn = QPushButton("Convert to Invoice")
        _stack(self.convert_btn)
        self.convert_btn.setEnabled(False)
        self.convert_btn.clicked.connect(self.convert_estimate_to_invoice)

        buttons_col.addStretch(1)

        root.addLayout(left, stretch=7)
        root.addWidget(center_widget, stretch=3)
        root.addLayout(buttons_col, stretch=1)

        self.load_invoices()

    # Router helpers
    def open_billing_for_appointment(self, appointment_id: int):
        try:
            inv_id = self._get_or_create_draft_invoice(appointment_id)
            self._opened_from_appointments = True
            self.new_invoice_btn.setEnabled(False)
            self.load_invoice_by_id(inv_id)
        except Exception as e:
            log_error(f"open_billing_for_appointment failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to open billing: {e}")

    def load_invoice_details(self, appointment_id: int):
        self.open_billing_for_appointment(appointment_id)

    def _get_or_create_draft_invoice(self, appointment_id: int) -> int:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT invoice_id
              FROM invoices
             WHERE appointment_id = ?
               AND invoice_type   = 'INVOICE'
             ORDER BY invoice_id DESC
             LIMIT 1
            """,
            (appointment_id,),
        )
        ex = cur.fetchone()
        if ex:
            conn.close()
            return ex[0]
        cur.execute(
            """
            INSERT INTO invoices (
                appointment_id, patient_id,
                invoice_type, total_amount, tax, discount, final_amount,
                payment_status, payment_method, invoice_date, created_at, remaining_balance,
                payable, revenue_eligible, inventory_deducted
            )
            SELECT a.appointment_id, a.patient_id,
                   'INVOICE', 0, 0, 0, 0,
                   'Unpaid', NULL, DATE('now'), CURRENT_TIMESTAMP, 0,
                   1, 1, 0
              FROM appointments a
             WHERE a.appointment_id = ?
            """,
            (appointment_id,),
        )
        inv_id = cur.lastrowid
        conn.commit()
        conn.close()
        return inv_id

    # NEW: walk-in invoice creation
    def _create_walkin_invoice(self, owner_name: str, owner_contact: str, owner_email: str) -> int:
        conn = _connect(); cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO invoices (
                invoice_date, appointment_id, patient_id,
                invoice_type, total_amount, tax, discount, final_amount,
                payment_status, payment_method, created_at, remaining_balance,
                payable, revenue_eligible, inventory_deducted,
                owner_name, owner_contact, owner_email
            )
            VALUES (DATE('now'), NULL, NULL,
                    'INVOICE', 0, 0, 0, 0,
                    'Unpaid', NULL, CURRENT_TIMESTAMP, 0,
                    1, 1, 0,
                    ?, ?, ?)
            """,
            (owner_name or None, owner_contact or None, owner_email or None),
        )
        inv_id = cur.lastrowid
        conn.commit(); conn.close()
        return inv_id

    def create_walkin_invoice(self):
        dlg = OwnerPicker(self)
        if dlg.exec() != QDialog.Accepted:
            return
        owner_name, owner_contact, owner_email = dlg.get_values()
        if not owner_name:
            QMessageBox.warning(self, "Missing Owner", "Please enter/select an owner name.")
            return
        try:
            inv_id = self._create_walkin_invoice(owner_name, owner_contact, owner_email)
            self._opened_from_appointments = False
            self.new_invoice_btn.setEnabled(True)
            self.load_invoice_by_id(inv_id)
            self.add_item_button.setEnabled(True)
            self._set_owner_snapshot(owner_contact, owner_email, show=True)
            QMessageBox.information(self, "Invoice Created", "Draft walk-in invoice created. Add items and Save.")
        except Exception as e:
            log_error(f"create_walkin_invoice failed: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create walk-in invoice: {e}")

    def _set_owner_snapshot(self, contact: str | None, email: str | None, show: bool):
        txt_parts = []
        if contact:
            txt_parts.append(contact)
        if email:
            txt_parts.append(email)
        self.owner_snapshot.setText(" • ".join(txt_parts))
        self.owner_snapshot.setVisible(show)
        self.owner_snapshot_lbl.setVisible(show)


    def _set_doc_mode(self, doc_row: dict):
        doc_type = (doc_row or {}).get("invoice_type", "INVOICE")
        payable = int((doc_row or {}).get("payable", 1) or 0)

        is_est = str(doc_type).upper() == "ESTIMATE"
        is_char = str(doc_type).upper() == "CHARITY"
        is_invoice = str(doc_type).upper() == "INVOICE"

        payments_enabled = payable == 1 and is_invoice

        self.view_payments_button.setEnabled(payments_enabled and self.selected_invoice_id is not None)
        self.add_payment_button.setEnabled(payments_enabled and self.selected_invoice_id is not None)
        self.delete_payment_button.setEnabled(False if not payments_enabled else self.delete_payment_button.isEnabled())

        self.payment_status_dropdown.setEnabled(is_invoice)
        self.payment_method_dropdown.setEnabled(is_invoice)

        self.convert_btn.setEnabled(is_est and self.selected_invoice_id is not None)
        # allow items regardless of appointment (for walk-ins)
        self.add_item_button.setEnabled(True)
        self.edit_item_button.setEnabled(self.item_table.currentRow() >= 0)
        self.delete_item_button.setEnabled(self.item_table.currentRow() >= 0)

        self.save_btn.setText("Save Invoice" if is_invoice else ("Save Estimate" if is_est else "Save Charity"))

    # Loading & filtering
    def load_invoices(self):
        try:
            conn = _connect()
            cur = conn.cursor()
            # CHANGED: LEFT JOIN appointments to include NULL appointment_id
            #          Patient/Owner fallback via COALESCE
            cur.execute(
                """
                SELECT i.invoice_id,
                       i.appointment_id,
                       COALESCE((SELECT name FROM patients WHERE patient_id = a.patient_id), i.owner_name) AS patient_or_owner,
                       i.total_amount,
                       i.final_amount,
                       i.payment_status,
                       i.payment_method,
                       (i.final_amount - COALESCE((SELECT SUM(amount_paid)
                             FROM payment_history
                            WHERE invoice_id = i.invoice_id), 0)) AS remaining,
                       i.owner_contact,
                       i.created_at
                  FROM invoices i
                  LEFT JOIN appointments a ON i.appointment_id = a.appointment_id
                 ORDER BY i.invoice_id DESC
                """
            )
            self.invoices = cur.fetchall()
            conn.close()
            self.apply_filters()
        except Exception as e:
            log_error(f"Database Error in load_invoices: {e}")
            QMessageBox.critical(self, "Database Error", f"An unexpected error occurred: {e}")

    def apply_filters(self):
        search = (self.search_input.text() or "").lower()
        status_filter = self.status_filter.currentText()
        start = self.start_date.date()
        end = self.end_date.date()

        filtered = []
        total_amount = 0.0
        remaining_sum = 0.0
        payment_count = 0

        for row in self.invoices:
            (
                invoice_id,
                appt_id,
                patient_or_owner,
                total_amt,
                final_amt,
                status,
                method,
                remaining,
                owner_contact,
                created_at,
            ) = row

            created_day = QDate.fromString((created_at or "").split(" ")[0], "yyyy-MM-dd")
            if created_day.isValid():
                if created_day < start or created_day > end:
                    continue

            if search:
                if (search not in str(appt_id).lower()) and (search not in (patient_or_owner or "").lower()) and (search not in (str(owner_contact) or "").lower()):
                    continue

            if status_filter == "Open" and str(status) == "Paid":
                continue
            if status_filter == "Paid" and str(status) != "Paid":
                continue

            filtered.append(row)

            if str(status).upper() not in ("ESTIMATE", "CHARITY", "N/A"):
                total_amount += float(final_amt or 0)
                remaining_sum += float(remaining or 0)
                if status != "Unpaid":
                    payment_count += 1

        self.invoice_table.setRowCount(0)
        for r, row in enumerate(filtered):
            self.invoice_table.insertRow(r)
            for c, val in enumerate(row):
                display = str(val)
                if c in (3, 4, 7):
                    try:
                        display = f"{float(val):.2f}"
                    except Exception:
                        pass
                item = QTableWidgetItem(display)
                if c == 5:
                    s = str(val).strip().lower()
                    if s == "paid":
                        item.setBackground(QtGui.QColor("#d4edda"))
                    elif s == "partially paid":
                        item.setBackground(QtGui.QColor("#fff3cd"))
                    elif s == "unpaid":
                        item.setBackground(QtGui.QColor("#f8d7da"))
                    elif s in ("estimate", "charity", "n/a"):
                        item.setBackground(QtGui.QColor("#e0e0f8"))
                self.invoice_table.setItem(r, c, item)

        self.total_amount_label.setText(f"Total: {total_amount:.2f}")
        self.remaining_balance_summary.setText(f"Remaining: {remaining_sum:.2f}")
        self.payment_count_label.setText(f"Payments: {payment_count}")

    def load_selected_invoice(self):
        sel = self.invoice_table.currentRow()
        if sel < 0:
            return
        inv_id = int(self.invoice_table.item(sel, 0).text())
        if not self._opened_from_appointments:
            self.new_invoice_btn.setEnabled(True)
        self.load_invoice_by_id(inv_id)

    def load_invoice_by_id(self, invoice_id: int):
        self.selected_invoice_id = int(invoice_id)
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT appointment_id, total_amount, tax, discount, final_amount, remaining_balance,
                   payment_status, payment_method, invoice_type, payable, inventory_deducted,
                   owner_name, owner_contact, owner_email
              FROM invoices
             WHERE invoice_id = ?
            """,
            (self.selected_invoice_id,),
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            QMessageBox.critical(self, "Error", "Could not load invoice details from the database.")
            return

        (
            appt_id,
            total_amt,
            _tax_unused,
            disc_pct,
            final_amt,
            rem_bal,
            status,
            method,
            invoice_type,
            payable,
            inventory_deducted,
            owner_name,
            owner_contact,
            owner_email,
        ) = row

        self.appointment_id_input.setText(str(appt_id or ""))
        # show owner/patient in label (fetch_patient_details will refine if appt exists)
        self.patient_name_label.setText(owner_name or "")
        # Show snapshot only when there is NO appointment
        self._set_owner_snapshot(owner_contact, owner_email, show=(not appt_id))
        self.total_amount_input.setText(f"{float(total_amt or 0):.2f}")
        self.discount_input.setValue(int(disc_pct or 0))
        self.final_amount_label.setText(f"{float(final_amt or 0):.2f}")
        self.remaining_balance_label.setText(f"{float(rem_bal or 0):.2f}")
        self.payment_status_dropdown.setCurrentText(str(status or "Unpaid"))
        self.payment_method_dropdown.setCurrentText(str(method or "Cash"))

        try:
            self.fetch_patient_details()
        except Exception:
            pass

        self.save_btn.setEnabled(True)
        self.delete_button.setEnabled(True)
        self.view_payments_button.setEnabled(True)
        self.add_payment_button.setEnabled(True)
        self.delete_payment_button.setEnabled(True)
        self.send_reminder_button.setEnabled(True)
        self.add_item_button.setEnabled(True)
        self.print_button.setEnabled(True)

        self.load_invoice_items()

        self._set_doc_mode(
            {
                "invoice_type": invoice_type,
                "payable": payable,
                "inventory_deducted": inventory_deducted,
            }
        )

        try:
            self.invoiceSelected.emit(self.selected_invoice_id)
        except Exception:
            pass

    # Item grid
    def _on_item_selection(self):
        has = self.item_table.currentRow() >= 0
        self.edit_item_button.setEnabled(has)
        self.delete_item_button.setEnabled(has)

    def load_invoice_items(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT description, quantity, unit_price, vat_amount, discount_amount, total_price
              FROM invoice_items
             WHERE invoice_id = ?
            """,
            (self.selected_invoice_id,),
        )
        items = cur.fetchall()
        conn.close()

        self.item_table.setRowCount(0)
        for row in items:
            r = self.item_table.rowCount()
            self.item_table.insertRow(r)
            for c, val in enumerate(row):
                if c == 2:
                    try:
                        display = f"{float(val):.4f}"
                    except Exception:
                        display = str(val)
                else:
                    display = str(val)
                self.item_table.setItem(r, c, QTableWidgetItem(display))

        self.item_count_label.setText(f"Items: {len(items)}")
        self.calculate_totals_from_items()
        self.calculate_final_amount()

    def add_item(self):
        dlg = ItemizedBillingDialog(self.selected_invoice_id, parent=self)
        if dlg.exec():
            self.load_invoice_items()

    def edit_item(self):
        r = self.item_table.currentRow()
        if r < 0:
            QMessageBox.warning(self, "No Item Selected", "Please select an item to edit.")
            return
        desc = self.item_table.item(r, 0).text()

        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT item_id FROM invoice_items WHERE description = ? AND invoice_id = ?",
            (desc, self.selected_invoice_id),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            QMessageBox.warning(self, "Error", "Could not find the selected item in the database.")
            return

        dlg = ItemizedBillingDialog(self.selected_invoice_id, item_id=row[0], parent=self)
        if dlg.exec():
            self.load_invoice_items()

    def delete_item(self):
        r = self.item_table.currentRow()
        if r < 0:
            QMessageBox.warning(self, "No Item Selected", "Please select an item to delete.")
            return
        if QMessageBox.question(self, "Delete Confirmation", "Delete this item?") != QMessageBox.Yes:
            return

        desc = self.item_table.item(r, 0).text()
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM invoice_items WHERE description = ? AND invoice_id = ?",
            (desc, self.selected_invoice_id),
        )
        conn.commit()
        conn.close()
        self.load_invoice_items()

    # Patient / appointment
    def _find_appointment(self):
        dlg = AppointmentPickerDialog(self)
        if dlg.exec() == QDialog.Accepted:
            appt_id = dlg.get_selected_id()
            if appt_id:
                self.appointment_id_input.setText(str(appt_id))

    def fetch_patient_details(self):
        appt = self.appointment_id_input.text().strip()
        if not appt:
            # Walk-in: load owner snapshot from invoice
            conn = _connect();
            cur = conn.cursor()
            cur.execute("SELECT owner_name, owner_contact, owner_email FROM invoices WHERE invoice_id=?",
                        (self.selected_invoice_id,))
            row = cur.fetchone()
            conn.close()
            owner_name = (row and row[0]) or ""
            owner_contact = (row and row[1]) or ""
            owner_email = (row and row[2]) or ""
            self.patient_name_label.setText(owner_name)
            self.date_label.clear()
            self.add_item_button.setEnabled(True)
            self._set_owner_snapshot(owner_contact, owner_email, show=True)
            return

        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.name, a.date_time
              FROM appointments a
              JOIN patients p ON a.patient_id = p.patient_id
             WHERE a.appointment_id = ?
            """,
            (appt,),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            self.patient_name_label.setText(row[0] or "")
            self.date_label.setText(row[1] or "")
            self.add_item_button.setEnabled(True)
            self._set_owner_snapshot(None, None, show=False)
        else:
            # fallback to owner if appt id invalid
            conn = _connect();
            cur = conn.cursor()
            cur.execute("SELECT owner_name FROM invoices WHERE invoice_id=?", (self.selected_invoice_id,))
            r2 = cur.fetchone()
            conn.close()
            self.patient_name_label.setText((r2 and r2[0]) or "")
            self.date_label.clear()
            self.add_item_button.setEnabled(True)
            self._set_owner_snapshot((r2 and r2[1]) or "", (r2 and r2[2]) or "", show=True)

    # Create docs
    def create_invoice(self):
        # unchanged: appointment-driven invoice flow
        appt = self.appointment_id_input.text().strip()
        if not appt:
            self._find_appointment()
            appt = self.appointment_id_input.text().strip()
            if not appt:
                QMessageBox.information(self, "No Appointment",
                                        "Please select an appointment to create an invoice.")
                return
        try:
            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT invoice_id FROM invoices WHERE appointment_id = ? AND invoice_type='INVOICE'",
                (appt,),
            )
            if cur.fetchone():
                conn.close()
                QMessageBox.information(
                    self, "Invoice Exists", "An invoice already exists for this appointment. Loading it."
                )
                conn = _connect()
                cur = conn.cursor()
                cur.execute(
                    "SELECT invoice_id FROM invoices WHERE appointment_id=? AND invoice_type='INVOICE' ORDER BY invoice_id DESC LIMIT 1",
                    (appt,),
                )
                row = cur.fetchone()
                conn.close()
                if row:
                    self.load_invoice_by_id(row[0])
                return

            cur.execute(
                """
                INSERT INTO invoices (
                    appointment_id, patient_id,
                    invoice_type, total_amount, tax, discount, final_amount,
                    payment_status, payment_method, invoice_date, created_at, remaining_balance,
                    payable, revenue_eligible, inventory_deducted
                )
                SELECT a.appointment_id, a.patient_id,
                       'INVOICE', 0, 0, 0, 0,
                       'Unpaid', NULL, DATE('now'), CURRENT_TIMESTAMP, 0,
                       1, 1, 0
                  FROM appointments a
                 WHERE a.appointment_id = ?
                """,
                (appt,),
            )
            new_id = cur.lastrowid
            conn.commit()
            conn.close()

            QMessageBox.information(self, "Invoice Created", "Draft invoice created. You can now add items.")
            self._opened_from_appointments = False
            self.new_invoice_btn.setEnabled(True)
            self.load_invoice_by_id(new_id)

        except Exception as e:
            log_error(f"Error in create_invoice: {e}")
            QMessageBox.critical(self, "Error", "Failed to create draft invoice.")

    def create_estimate(self):
        try:
            appt = self.appointment_id_input.text().strip()
            if not appt:
                self._find_appointment()
                appt = self.appointment_id_input.text().strip()
                if not appt:
                    QMessageBox.information(self, "No Appointment",
                                            "Please select an appointment to create an estimate.")
                    return

            conn = _connect()
            cur = conn.cursor()
            cur.execute("SELECT invoice_id FROM invoices WHERE appointment_id=? AND invoice_type='ESTIMATE'", (appt,))
            if cur.fetchone():
                conn.close()
                QMessageBox.information(self, "Already Exists", f"An ESTIMATE already exists for appointment {appt}.")
                return

            cur.execute(
                """
                INSERT INTO invoices (
                    appointment_id, patient_id,
                    invoice_type, total_amount, tax, discount, final_amount,
                    payment_status, payment_method, invoice_date, created_at, remaining_balance,
                    payable, revenue_eligible, inventory_deducted, estimate_number
                )
                SELECT a.appointment_id, a.patient_id,
                       'ESTIMATE', 0, 0, 0, 0,
                       'N/A', NULL, DATE('now'), CURRENT_TIMESTAMP, 0,
                       0, 0, 0, NULL
                  FROM appointments a
                 WHERE a.appointment_id = ?
                """,
                (appt,),
            )
            new_id = cur.lastrowid
            conn.commit()
            conn.close()

            QMessageBox.information(
                self, "Estimate Created", "Draft estimate created. Add items and print/share as needed."
            )
            self.load_invoice_by_id(new_id)

        except Exception as e:
            log_error(f"Error in create_estimate: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create estimate: {e}")

    def create_charity(self):
        try:
            appt = self.appointment_id_input.text().strip()
            if not appt:
                self._find_appointment()
                appt = self.appointment_id_input.text().strip()
                if not appt:
                    QMessageBox.information(self, "No Appointment",
                                            "Please select an appointment to create a charity doc.")
                    return

            conn = _connect()
            cur = conn.cursor()
            cur.execute("SELECT invoice_id FROM invoices WHERE appointment_id=? AND invoice_type='CHARITY'", (appt,))
            if cur.fetchone():
                conn.close()
                QMessageBox.information(self, "Already Exists", f"A CHARITY doc already exists for appointment {appt}.")
                return

            cur.execute(
                """
                INSERT INTO invoices (
                    appointment_id, patient_id,
                    invoice_type, total_amount, tax, discount, final_amount,
                    payment_status, payment_method, invoice_date, created_at, remaining_balance,
                    payable, revenue_eligible, inventory_deducted, charity_number
                )
                SELECT a.appointment_id, a.patient_id,
                       'CHARITY', 0, 0, 0, 0,
                       'N/A', NULL, DATE('now'), CURRENT_TIMESTAMP, 0,
                       0, 0, 0, NULL
                  FROM appointments a
                 WHERE a.appointment_id = ?
                """,
                (appt,),
            )
            new_id = cur.lastrowid
            conn.commit()
            conn.close()

            QMessageBox.information(
                self,
                "Charity Created",
                "Draft charity document created. Add items; stock deducts on first save.",
            )
            self.load_invoice_by_id(new_id)

        except Exception as e:
            log_error(f"Error in create_charity: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create charity document: {e}")


    # Save / inventory deduction
    def edit_invoice(self):
        if not self.selected_invoice_id:
            QMessageBox.warning(self, "No Document", "Please select a document to save.")
            return

        # CHANGED: appointment is optional
        appt_txt = self.appointment_id_input.text().strip()
        appointment_id = int(appt_txt) if appt_txt.isdigit() else None

        conn = None
        try:
            total_amount, final_amount = self.calculate_totals_from_items()
            disc = self.discount_input.value()
            payment_status = self.payment_status_dropdown.currentText()
            payment_method = self.payment_method_dropdown.currentText()

            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT invoice_type, payable, inventory_deducted FROM invoices WHERE invoice_id = ?",
                (self.selected_invoice_id,),
            )
            row = cur.fetchone()
            if not row:
                conn.close()
                QMessageBox.warning(self, "Not Found", "Document not found.")
                return
            doc_type, payable_flag, already_deducted = row[0], int(row[1] or 0), int(row[2] or 0)

            # CHANGED: update with nullable appointment_id
            cur.execute(
                """
                UPDATE invoices
                   SET appointment_id = ?,
                       total_amount   = ?,
                       tax            = 0,
                       discount       = ?,
                       final_amount   = ?,
                       payment_status = ?,
                       payment_method = ?
                 WHERE invoice_id = ?
                """,
                (
                    appointment_id,
                    total_amount,
                    disc,
                    final_amount,
                    payment_status,
                    payment_method,
                    self.selected_invoice_id,
                ),
            )

            # items rewrite (unchanged)
            cur.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (self.selected_invoice_id,))
            for r in range(self.item_table.rowCount()):
                desc = self.item_table.item(r, 0).text().strip()
                qty = int(float(self.item_table.item(r, 1).text()))
                unit_net = float(self.item_table.item(r, 2).text())
                vat_amt = float(self.item_table.item(r, 3).text())
                disc_amt = float(self.item_table.item(r, 4).text())
                total = float(self.item_table.item(r, 5).text())

                base_before_disc = unit_net * qty
                disc_frac = 0.0 if base_before_disc <= 0 else (disc_amt / base_before_disc)
                net_after_disc = base_before_disc - disc_amt
                vat_frac = 0.0 if net_after_disc <= 0 else (vat_amt / net_after_disc)
                rate = int(round(vat_frac * 100))
                flag = "B" if rate == 5 else "C" if rate == 19 else ""

                cur.execute(
                    """
                    INSERT INTO invoice_items
                      (invoice_id, description, quantity, unit_price,
                       vat_pct, vat_amount, discount_pct, discount_amount,
                       total_price, vat_flag)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        self.selected_invoice_id,
                        desc,
                        qty,
                        unit_net,
                        vat_frac,
                        vat_amt,
                        disc_frac,
                        disc_amt,
                        total,
                        flag,
                    ),
                )

            # inventory (unchanged)
            if str(doc_type).upper() in ("INVOICE", "CHARITY") and already_deducted == 0:
                reason_prefix = f"Dispensed via {str(doc_type).title()} #{self.selected_invoice_id}"
                for r in range(self.item_table.rowCount()):
                    desc = self.item_table.item(r, 0).text().strip()
                    qty = int(float(self.item_table.item(r, 1).text()))
                    if qty <= 0:
                        continue
                    cur.execute("SELECT item_id FROM items WHERE name = ?", (desc,))
                    rec = cur.fetchone()
                    if not rec:
                        continue
                    item_id = rec[0]
                    reason = f"{reason_prefix} — {qty}×{desc}"
                    cur.execute(
                        "SELECT COUNT(*) FROM stock_movements WHERE item_id=? AND reason=?",
                        (item_id, reason),
                    )
                    if (cur.fetchone() or [0])[0]:
                        continue
                    ts = datetime.now().isoformat(" ", "seconds")
                    cur.execute(
                        """
                        INSERT INTO stock_movements (item_id, change_qty, reason, timestamp)
                        VALUES (?,?,?,?)
                        """,
                        (item_id, -qty, reason, ts),
                    )
                cur.execute(
                    "UPDATE invoices SET inventory_deducted = 1 WHERE invoice_id = ?",
                    (self.selected_invoice_id,),
                )

            if payable_flag == 0:
                cur.execute(
                    """
                    UPDATE invoices
                       SET remaining_balance = 0,
                           payment_status    = 'N/A'
                     WHERE invoice_id = ?
                    """,
                    (self.selected_invoice_id,),
                )

            conn.commit()
            self.update_payment_status_and_balance(self.selected_invoice_id, final_amount)

            QMessageBox.information(self, "Saved", "Document saved successfully.")
            self.load_invoices()
            self.calculate_final_amount()

        except Exception as e:
            if conn:
                conn.rollback()
            log_error(f"Save #{getattr(self, 'selected_invoice_id', 'N/A')} failed: {e}")
            QMessageBox.critical(self, "Error", f"Unexpected error: {e}")
        finally:
            if conn:
                conn.close()

    def convert_estimate_to_invoice(self):
        if not self.selected_invoice_id:
            QMessageBox.warning(self, "No Document", "Please select a document first.")
            return

        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT invoice_type, inventory_deducted
              FROM invoices
             WHERE invoice_id=?
            """,
            (self.selected_invoice_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            QMessageBox.warning(self, "Not Found", "Record not found.")
            return

        itype, already_deducted = str(row[0] or ""), int(row[1] or 0)
        if itype.upper() != "ESTIMATE":
            conn.close()
            QMessageBox.information(self, "Not an Estimate", "Only estimates can be converted.")
            return

        if (
            QMessageBox.question(
                self,
                "Convert to Invoice",
                "Convert this estimate to a real invoice? This enables payments and may deduct stock once.",
            )
            != QMessageBox.Yes
        ):
            conn.close()
            return

        try:
            cur.execute(
                """
                UPDATE invoices
                   SET invoice_type='INVOICE',
                       revenue_eligible=1,
                       payable=1,
                       payment_status='Unpaid'
                 WHERE invoice_id=?
                """,
                (self.selected_invoice_id,),
            )

            if already_deducted == 0:
                reason_prefix = f"Dispensed via Invoice #{self.selected_invoice_id}"
                cur.execute(
                    """
                    SELECT description, quantity
                      FROM invoice_items
                     WHERE invoice_id=?
                    """,
                    (self.selected_invoice_id,),
                )
                rows = cur.fetchall()

                for desc, qty in rows:
                    try:
                        q = int(qty)
                    except Exception:
                        continue
                    if q <= 0:
                        continue

                    cur.execute("SELECT item_id FROM items WHERE name=?", (str(desc).strip(),))
                    rec = cur.fetchone()
                    if not rec:
                        continue
                    item_id = rec[0]

                    reason = f"{reason_prefix} - {q}×{str(desc).strip()}"
                    cur.execute(
                        "SELECT COUNT(*) FROM stock_movements WHERE item_id=? AND reason=?",
                        (item_id, reason),
                    )
                    if (cur.fetchone() or [0])[0]:
                        continue

                    ts = datetime.now().isoformat(" ", "seconds")
                    cur.execute(
                        """
                        INSERT INTO stock_movements (item_id, change_qty, reason, timestamp)
                        VALUES (?,?,?,?)
                        """,
                        (item_id, -q, reason, ts),
                    )

                cur.execute(
                    "UPDATE invoices SET inventory_deducted=1 WHERE invoice_id=?",
                    (self.selected_invoice_id,),
                )

            conn.commit()

        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "Error", f"Conversion failed: {e}")
            return
        finally:
            conn.close()

        QMessageBox.information(self, "Converted", "Estimate converted to Invoice successfully.")
        self.load_invoices()
        self.load_selected_invoice()

    # Payments & reminders
    def view_payment_history(self):
        if not self.selected_invoice_id:
            QMessageBox.warning(self, "No Invoice Selected", "Please select an invoice to view payment history.")
            return
        PaymentHistoryDialog(self.selected_invoice_id, self).exec()

    def add_payment(self):
        if not self.selected_invoice_id:
            QMessageBox.warning(self, "No Invoice Selected", "Please select a document to add a payment.")
            return

        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT payable, invoice_type FROM invoices WHERE invoice_id = ?",
            (self.selected_invoice_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            QMessageBox.warning(self, "Not Found", "Document not found.")
            return
        payable, inv_type = int(row[0] or 0), str(row[1] or "INVOICE")
        if payable == 0:
            conn.close()
            QMessageBox.information(
                self,
                "Not Payable",
                f"This {inv_type.title()} is non-payable. Payments are disabled.",
            )
            return

        cur.execute(
            """
            SELECT final_amount - COALESCE((SELECT SUM(amount_paid) FROM payment_history WHERE invoice_id = ?), 0)
              FROM invoices
             WHERE invoice_id = ?
            """,
            (self.selected_invoice_id, self.selected_invoice_id),
        )
        remaining = float(cur.fetchone()[0] or 0)
        conn.close()

        if remaining <= 0:
            QMessageBox.information(self, "No Balance", "This invoice is already fully paid.")
            return

        dlg = AddPaymentDialog(self.selected_invoice_id, remaining, self)
        if dlg.exec():
            self.load_invoices()
            self.load_selected_invoice()

    def delete_payment(self):
        dlg = PaymentHistoryDialog(self.selected_invoice_id, self)
        btn = QPushButton("Delete Selected")
        btn.setStyleSheet(BTN_STYLE)
        dlg.layout().addWidget(btn)

        def _go():
            row = dlg.payment_table.currentRow()
            if row < 0:
                QMessageBox.warning(dlg, "No Payment", "Select one to delete.")
                return
            payment_date = dlg.payment_table.item(row, 0).text()
            amount = dlg.payment_table.item(row, 1).text()

            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                """
                DELETE FROM payment_history
                 WHERE invoice_id=? AND payment_date=? AND amount_paid=?
                """,
                (self.selected_invoice_id, payment_date, amount),
            )
            conn.commit()
            conn.close()

            dlg.load_payment_history()
            final = float(self.final_amount_label.text() or 0)
            self.update_payment_status_and_balance(self.selected_invoice_id, final)
            self.load_invoices()
            self.load_selected_invoice()

        btn.clicked.connect(_go)
        dlg.exec()

    def send_invoice_reminder(self):
        if not self.selected_invoice_id:
            QMessageBox.warning(self, "No Invoice Selected", "Please select an invoice first.")
            return
        appt_txt = self.appointment_id_input.text().strip()
        if not appt_txt.isdigit():
            QMessageBox.information(self, "No Appointment", "Reminders require an appointment.")
            return
        appt_id = int(appt_txt)
        dlg = InvoiceReminderDialog(self.selected_invoice_id, self)
        if dlg.exec() != QDialog.Accepted:
            return
        rem_time, reason = dlg.get_values()
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO reminders (appointment_id, reminder_time, reminder_status, reminder_reason)
            VALUES (?, ?, 'Pending', ?)
            """,
            (appt_id, rem_time, reason),
        )
        conn.commit()
        conn.close()
        QMessageBox.information(
            self, "Reminder Scheduled", f"Payment reminder set for {rem_time}.\nReason: {reason}"
        )

    # Delete
    def delete_invoice(self):
        if not self.selected_invoice_id:
            QMessageBox.warning(self, "No Invoice Selected", "Please select an invoice to delete.")
            return
        if (
            QMessageBox.question(
                self, "Delete Confirmation", "Are you sure you want to delete this invoice?"
            )
            != QMessageBox.Yes
        ):
            return
        conn = _connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM invoices WHERE invoice_id = ?", (self.selected_invoice_id,))
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Success", "Invoice deleted successfully.")
        self.load_invoices()
        self.clear_inputs()
        self.clear_invoice_form()

    # Printing / PDFs
    def _collect_invoice_print_payload(self):
        """
        Returns a dict with all data needed for PDF building/printing.
        Falls back to owner snapshot if there's no appointment/patient.
        """
        inv_id = self.selected_invoice_id

        # Owner & pet
        appt_id = int(self.appointment_id_input.text() or 0) if (
                self.appointment_id_input.text() or "").isdigit() else None
        owner_name = "";
        owner_contact = "";
        pet_name = ""
        if appt_id:
            conn = _connect();
            cur = conn.cursor()
            cur.execute(
                """
                SELECT p.owner_name, p.owner_contact, p.name
                  FROM appointments a
                  JOIN patients   p ON a.patient_id = p.patient_id
                 WHERE a.appointment_id = ?
                """,
                (appt_id,),
            )
            owner_name, owner_contact, pet_name = cur.fetchone() or ("", "", "")
            conn.close()
        else:
            # walk-in: pull snapshot from invoices
            conn = _connect();
            cur = conn.cursor()
            cur.execute(
                "SELECT owner_name, owner_contact FROM invoices WHERE invoice_id=?",
                (inv_id,),
            )
            row = cur.fetchone()
            conn.close()
            owner_name = (row and row[0]) or ""
            owner_contact = (row and row[1]) or ""
            pet_name = ""

        # Items (incl VAT per line)
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT description, quantity, unit_price,
                   discount_pct, discount_amount,
                   total_price,
                   vat_pct, vat_amount, vat_flag
              FROM invoice_items
             WHERE invoice_id = ?
            """,
            (inv_id,),
        )
        raw_items = cur.fetchall()
        conn.close()

        items = [
            {
                "desc": desc,
                "qty": qty,
                "unit": unit,
                "disc_amt": d_amt,
                "total": total,
                "vat_amt": v_amt,
            }
            for desc, qty, unit, d_pct, d_amt, total, v_pct, v_amt, v_flag in raw_items
        ]

        # VAT breakdown & totals
        grouping = {}
        net_excl_vat = 0.0
        vat_total = 0.0
        for desc, qty, unit, d_pct, d_amt, total, v_pct, v_amt, v_flag in raw_items:
            net = float(total or 0) - float(v_amt or 0)
            net_excl_vat += net
            vat_total += float(v_amt or 0)
            grp = grouping.setdefault(v_pct, {"net": 0.0, "vat_amount": 0.0, "flag": v_flag})
            grp["net"] += net
            grp["vat_amount"] += float(v_amt or 0)

        vat_breakdown = [
            {"vat_pct": rate, "net": data["net"], "vat_amount": data["vat_amount"], "flag": data["flag"]}
            for rate, data in grouping.items()
        ]

        # Header values & cumulative payments
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COALESCE(discount,0), COALESCE(final_amount,0),
                   COALESCE(invoice_type,'INVOICE'), COALESCE(payment_status,'Unpaid')
              FROM invoices
             WHERE invoice_id = ?
            """,
            (inv_id,),
        )
        disc_pct, final_total, doc_type, status = cur.fetchone() or (0.0, 0.0, "INVOICE", "Unpaid")

        cur.execute(
            "SELECT COALESCE(SUM(amount_paid),0) FROM payment_history WHERE invoice_id = ?",
            (inv_id,),
        )
        paid_amount = float((cur.fetchone() or [0])[0] or 0.0)
        conn.close()

        subtotal = sum(float(it["total"] or 0) for it in items)  # gross (incl VAT)
        discount_amount = float(subtotal) * (float(disc_pct or 0) / 100.0)
        computed_total = float(final_total or (subtotal - discount_amount))
        balance_due = max(computed_total - paid_amount, 0.0)

        return {
            "inv_id": inv_id,
            "owner_name": owner_name,
            "pet_name": pet_name,
            "items": items,
            "vat_breakdown": vat_breakdown,
            "subtotal": float(subtotal or 0),
            "disc_pct": float(disc_pct or 0),
            "discount_amount": float(discount_amount or 0),
            "final_total": float(computed_total),
            "doc_type": doc_type,
            "net_excl_vat": float(net_excl_vat or 0),
            "vat_total": float(vat_total or 0),
            "paid_amount": float(paid_amount or 0),
            "balance_due": float(balance_due or 0),
            "status": status,
        }

    def print_invoice(self):
        if not self.selected_invoice_id:
            QMessageBox.warning(self, "No Invoice", "Please select an invoice first.")
            return

        payload = self._collect_invoice_print_payload()
        inv_id = payload["inv_id"]
        owner_name = payload["owner_name"]
        created_date = datetime.now().strftime("%d-%b-%Y")
        created_time = datetime.now().strftime("%H:%M")

        layout_msg = QMessageBox(self)
        layout_msg.setWindowTitle("Choose Layout")
        layout_msg.setText("Which layout would you like to use?")
        a4_btn = layout_msg.addButton("A4 (Full Page)", QMessageBox.AcceptRole)
        thermal_btn = layout_msg.addButton("Thermal 80 mm", QMessageBox.AcceptRole)
        layout_msg.addButton("Cancel", QMessageBox.RejectRole)
        layout_msg.exec()
        if layout_msg.clickedButton() not in (a4_btn, thermal_btn):
            return
        is_a4 = layout_msg.clickedButton() is a4_btn

        out_msg = QMessageBox(self)
        out_msg.setWindowTitle("Invoice Output")
        out_msg.setText("Save as PDF or send directly to printer?")
        pdf_btn = out_msg.addButton("Save as PDF", QMessageBox.AcceptRole)
        print_btn = out_msg.addButton("Print to Printer", QMessageBox.AcceptRole)
        out_msg.addButton("Cancel", QMessageBox.RejectRole)
        out_msg.exec()
        clicked = out_msg.clickedButton()
        if clicked not in (pdf_btn, print_btn):
            return

        if clicked is pdf_btn:
            default_fn = f"Invoice_{inv_id}_{owner_name.replace(' ', '')}_{datetime.now():%Y%m%d}.pdf"
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Invoice as PDF", default_fn, "PDF Files (*.pdf)"
            )
            if not path:
                return
            try:
                if is_a4:
                    self._generate_pdf_a4(
                        path=path, created_date=created_date, created_time=created_time, **payload
                    )
                else:
                    self._generate_pdf_thermal(
                        path=path, created_date=created_date, created_time=created_time, **payload
                    )
                QMessageBox.information(self, "Saved", f"Invoice saved to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not create PDF:\n{e}")
            return

        tmp_path = os.path.join(
            tempfile.gettempdir(), f"Invoice_{inv_id}_{owner_name.replace(' ', '')}.pdf"
        )
        if is_a4:
            self._generate_pdf_a4(
                path=tmp_path, created_date=created_date, created_time=created_time, **payload
            )
            try:
                os.startfile(tmp_path, "print")
            except Exception as e:
                QMessageBox.critical(self, "Print Error", f"Couldn't send to the default printer:\n{e}")
        else:
            self._generate_pdf_thermal(
                path=tmp_path, created_date=created_date, created_time=created_time, **payload
            )
            thermal_name = None
            for pi in QPrinterInfo.availablePrinters():
                n = pi.printerName().lower()
                if "thermal" in n or "epson" in n:
                    thermal_name = pi.printerName()
                    break
            if not thermal_name:
                QMessageBox.warning(
                    self,
                    "Printer Not Found",
                    "Could not find your thermal printer. Ensure its driver is installed and the name contains Thermal Epson"
                )
                return
            original = win32print.GetDefaultPrinter()
            try:
                win32print.SetDefaultPrinter(thermal_name)
                os.startfile(tmp_path, "print")
            finally:
                win32print.SetDefaultPrinter(original)

    # PDF builders (include Excel-like block)
    def _generate_pdf_thermal(
        self,
        path,
        inv_id,
        created_date,
        created_time,
        owner_name,
        pet_name,
        items,
        subtotal,
        disc_pct,
        final_total,
        vat_breakdown,
        doc_type,
        net_excl_vat,
        vat_total,
        paid_amount,
        balance_due,
        status,
        **_,
    ):
        width, margin = 80 * mm, 5 * mm
        cw = width - 2 * margin
        styles = getSampleStyleSheet()
        styles["Normal"].fontName = "Courier"
        styles["Normal"].fontSize = 6
        styles["Title"].fontName = "Courier-Bold"
        styles["Title"].fontSize = 9

        elems = []

        # Logo
        logo_fp = _find_logo_path()
        if logo_fp:
            try:
                img = Image(logo_fp, width=cw * 0.6, height=cw * 0.3)
                img.hAlign = "CENTER"
                elems += [img, Spacer(1, 6 * mm)]
            except Exception as e:
                log_error(f"Logo load failed: {e}")

        # Clinic header
        elems.append(Paragraph("PET WELLNESS VETS", styles["Title"]))
        elems.append(Paragraph("Kyriakou Adamou no.2, Shop 2&3, 8220", styles["Normal"]))
        elems.append(Paragraph("Tel: 99941186   Email: contact@petwellnessvets.com", styles["Normal"]))
        elems.append(Spacer(1, 3 * mm))

        # Title
        title_map = {"INVOICE": "INVOICE", "ESTIMATE": "ESTIMATE", "CHARITY": "CHARITY / PRO BONO"}
        elems.append(Paragraph(title_map.get(str(doc_type).upper(), "INVOICE"), styles["Title"]))
        elems.append(Spacer(1, 2 * mm))

        # Meta
        meta = [
            ["Inv#:", str(inv_id), "Date:", created_date],
            ["Time:", created_time, "Customer:", owner_name],
            ["Pet:", pet_name, "", ""],
        ]
        meta_tbl = Table(meta, colWidths=[cw * 0.20, cw * 0.30, cw * 0.20, cw * 0.30])
        meta_tbl.setStyle(TableStyle([["FONTSIZE", (0, 0), (-1, -1), 7], ["BOTTOMPADDING", (0, 0), (-1, -1), 2]]))
        elems += [meta_tbl, Spacer(1, 3 * mm)]

        # Items
        data = [["Desc", "Qty", "Unit", "Disc", "Total", "VAT"]]
        for it in items:
            data.append(
                [
                    it["desc"],
                    str(it["qty"]),
                    f"{float(it['unit']):.2f}",
                    f"{float(it['disc_amt']):.2f}",
                    f"{float(it['total']):.2f}",
                    f"{float(it['vat_amt']):.2f}",
                ]
            )
        itbl = Table(
            data,
            colWidths=[cw * 0.40, cw * 0.10, cw * 0.15, cw * 0.10, cw * 0.15, cw * 0.10],
        )
        itbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.black),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        elems += [itbl, Spacer(1, 3 * mm)]

        # VAT breakdown
        vat_data = [["Net", "VAT%", "VAT", "Flag"]]
        for row in vat_breakdown:
            vat_data.append(
                [
                    f"{float(row['net'] or 0):.2f}",
                    f"{row['vat_pct']:.2f}%",
                    f"{float(row['vat_amount'] or 0):.2f}",
                    row["flag"],
                ]
            )
        vat_data.append(["", "", "Total VAT", f"€{float(vat_total or 0):.2f}"])
        vtbl = Table(vat_data, colWidths=[cw * 0.40, cw * 0.20, cw * 0.20, cw * 0.20])
        vtbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.black),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        elems += [vtbl, Spacer(1, 3 * mm)]

        # Accounting block
        gross_subtotal = sum(float(it["total"] or 0) for it in items)
        disc_pct_val = float(disc_pct or 0)
        discount_amount = gross_subtotal * (disc_pct_val / 100.0)

        accounting = [
            ["Subtotal (Excl. VAT):", f"€{float(net_excl_vat or 0):.2f}"],
            ["VAT Total:", f"€{float(vat_total or 0):.2f}"],
            ["Gross Subtotal (Incl. VAT):", f"€{gross_subtotal:.2f}"],
        ]
        if disc_pct_val > 0:
            accounting.append([f"Invoice Discount ({disc_pct_val:.0f}%):", f"–€{discount_amount:.2f}"])
        accounting += [
            ["Total (Incl. VAT):", f"€{float(final_total or gross_subtotal):.2f}"],
            ["Amount Paid:", f"€{float(paid_amount or 0):.2f}"],
            ["Balance Due:", f"€{float(balance_due or 0):.2f}"],
            ["Status:", status],
        ]
        atbl = Table(accounting, colWidths=[cw * 0.60, cw * 0.40], hAlign="RIGHT")
        atbl.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        elems += [atbl, Spacer(1, 3 * mm)]

        # Non-payable note
        if str(doc_type).upper() == "ESTIMATE":
            elems.append(
                Paragraph(
                    "This is a non-binding estimate. No payment due. Stock is not reserved and may change.",
                    styles["Normal"],
                )
            )
            elems.append(Spacer(1, 2 * mm))
        elif str(doc_type).upper() == "CHARITY":
            elems.append(
                Paragraph("Charity / pro bono document. No payment due (clinic-sponsored).", styles["Normal"])
            )
            elems.append(Spacer(1, 2 * mm))

        # Signatures
        sig = [["Doctor:", "Issued By:", "Received By:"], ["____", "____", "____"]]
        s_tbl = Table(sig, colWidths=[cw / 3] * 3)
        s_tbl.setStyle(TableStyle([["FONTSIZE", (0, 0), (-1, -1), 7], ["BOTTOMPADDING", (0, 0), (2, 0), 4]]))
        elems.append(s_tbl)

        # Auto height
        total_h = margin * 2
        for f in elems:
            _, h = f.wrap(cw, A4[1])
            total_h += h

        doc = SimpleDocTemplate(
            path,
            pagesize=(width, total_h),
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
        )
        doc.build(elems)

    def _generate_pdf_a4(
        self,
        path,
        inv_id,
        created_date,
        created_time,
        owner_name,
        pet_name,
        items,
        subtotal,
        disc_pct,
        final_total,
        vat_breakdown,
        doc_type,
        net_excl_vat,
        vat_total,
        paid_amount,
        balance_due,
        status,
        **_,
    ):
        doc = SimpleDocTemplate(
            path,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=15 * mm,
        )
        styles = getSampleStyleSheet()
        h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14, leading=16, spaceAfter=6)
        small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, leading=11)

        elems = []

        # Header with logo on the right
        clinic_left = [
            Paragraph("<b>PET WELLNESS VETS</b>", h1),
            Paragraph("Kyriakou Adamou no.2, Shop 2&3, 8220", small),
            Paragraph("Tel: 99941186", small),
            Paragraph("Email: contact@petwellnessvets.com", small),
        ]
        logo_fp = _find_logo_path()
        logo_cell = [Image(logo_fp, width=35 * mm, height=18 * mm)] if logo_fp else []
        header_tbl = Table([[clinic_left, logo_cell]], colWidths=[120 * mm, 49 * mm])
        header_tbl.setStyle(
            TableStyle(
                [
                    ["VALIGN", (0, 0), (-1, -1), "TOP"],
                    ["ALIGN", (1, 0), (1, 0), "RIGHT"],
                ]
            )
        )
        elems += [header_tbl, Spacer(1, 6 * mm)]

        # Title & meta
        title_map = {"INVOICE": "INVOICE", "ESTIMATE": "ESTIMATE", "CHARITY": "CHARITY / PRO BONO"}
        title = title_map.get(str(doc_type).upper(), "INVOICE")
        meta_tbl = Table(
            [
                [Paragraph(f"<b>{title}</b>", styles["Title"]), ""],
                ["Invoice #:", str(inv_id)],
                ["Date:", created_date],
                ["Time:", created_time],
                ["Customer:", owner_name],
                ["Pet:", pet_name],
            ],
            colWidths=[35 * mm, 134 * mm],
        )
        meta_tbl.setStyle(TableStyle([["BOTTOMPADDING", (0, 0), (-1, -1), 3], ["FONTSIZE", (0, 1), (-1, -1), 10]]))
        elems += [meta_tbl, Spacer(1, 8 * mm)]

        # Items table
        data = [["Description", "Qty", "Unit (net €)", "Discount (€)", "VAT (€)", "Line Total (€)"]]
        for it in items:
            data.append(
                [
                    it["desc"],
                    str(it["qty"]),
                    f"{float(it['unit']):.2f}",
                    f"{float(it['disc_amt']):.2f}",
                    f"{float(it['vat_amt']):.2f}",
                    f"{float(it['total']):.2f}",
                ]
            )
        itbl = Table(data, colWidths=[90 * mm, 15 * mm, 22 * mm, 24 * mm, 20 * mm, 28 * mm])
        itbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.black),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                    ("GRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#c8c8c8")),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                ]
            )
        )
        elems += [itbl, Spacer(1, 8 * mm)]

        # VAT breakdown
        vat_data = [["Net (€)", "VAT %", "VAT (€)", "Flag"]]
        for v in vat_breakdown:
            vat_data.append(
                [
                    f"{float(v['net'] or 0):.2f}",
                    f"{v['vat_pct']:.2f}%",
                    f"{float(v['vat_amount'] or 0):.2f}",
                    v["flag"],
                ]
            )
        vat_data.append(["", "", "Total VAT", f"€{float(vat_total or 0):.2f}"])
        vtbl = Table(vat_data, colWidths=[40 * mm, 20 * mm, 30 * mm, 20 * mm])
        vtbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8c8c8")),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                ]
            )
        )
        elems += [vtbl, Spacer(1, 8 * mm)]

        # Accounting block
        gross_subtotal = sum(float(it["total"] or 0) for it in items)
        disc_pct_val = float(disc_pct or 0)
        discount_amount = gross_subtotal * (disc_pct_val / 100.0)

        accounting = [
            ["Subtotal (Excl. VAT):", f"€{float(net_excl_vat or 0):.2f}"],
            ["VAT Total:", f"€{float(vat_total or 0):.2f}"],
            ["Gross Subtotal (Incl. VAT):", f"€{gross_subtotal:.2f}"],
        ]
        if disc_pct_val > 0:
            accounting.append([f"Invoice Discount ({disc_pct_val:.0f}%):", f"-€{discount_amount:.2f}"])
        accounting += [
            ["Total (Incl. VAT):", f"€{float(final_total or gross_subtotal):.2f}"],
            ["Amount Paid:", f"€{float(paid_amount or 0):.2f}"],
            ["Balance Due:", f"€{float(balance_due or 0):.2f}"],
            ["Status:", status],
        ]
        audit_tbl = Table(accounting, colWidths=[60 * mm, 40 * mm], hAlign="RIGHT")
        audit_tbl.setStyle(
            TableStyle(
                [
                    ["ALIGN", (1, 0), (1, -1), "RIGHT"],
                    ["FONTSIZE", (0, 0), (-1, -1), 11],
                    ["BOTTOMPADDING", (0, 0), (-1, -1), 2],
                ]
            )
        )
        elems += [audit_tbl, Spacer(1, 6 * mm)]

        # Non-payable note
        if str(doc_type).upper() == "ESTIMATE":
            elems += [
                Paragraph(
                    "This is a non-binding estimate. No payment due. Stock is not reserved and may change.",
                    small,
                ),
                Spacer(1, 4 * mm),
            ]
        elif str(doc_type).upper() == "CHARITY":
            elems += [
                Paragraph("Charity / pro bono document. No payment due (clinic-sponsored).", small),
                Spacer(1, 4 * mm),
            ]

        # Signatures
        sig_tbl = Table(
            [["Doctor:", "Issued By:", "Received By:"], ["__________________", "__________________", "__________________"]],
            colWidths=[60 * mm, 60 * mm, 49 * mm],
        )
        sig_tbl.setStyle(TableStyle([["FONTSIZE", (0, 0), (-1, -1), 10]]))
        elems.append(sig_tbl)

        doc.build(elems)

    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    # Totals / status helpers / export / clear
    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    def calculate_final_amount(self):
        try:
            total = float(self.total_amount_input.text() or 0)
            disc = self.discount_input.value() / 100.0
            final_amount = total - (total * disc)
            self.final_amount_label.setText(f"{final_amount:.2f}")

            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COALESCE(SUM(amount_paid), 0)
                  FROM payment_history
                 WHERE invoice_id = ?
                """,
                (self.selected_invoice_id,),
            )
            paid = float(cur.fetchone()[0] or 0)
            conn.close()

            remaining = final_amount - paid
            self.remaining_balance_label.setText(f"{remaining:.2f}")

            if remaining <= 0:
                self.payment_status_dropdown.setCurrentText("Paid")
            elif remaining < final_amount:
                self.payment_status_dropdown.setCurrentText("Partially Paid")
            else:
                self.payment_status_dropdown.setCurrentText("Unpaid")

        except Exception:
            self.final_amount_label.setText("0.00")
            self.remaining_balance_label.setText("0.00")

    def calculate_totals_from_items(self):
        total = 0.0
        for r in range(self.item_table.rowCount()):
            try:
                total += float(self.item_table.item(r, 5).text())
            except Exception:
                pass
        self.total_amount_input.setText(f"{total:.2f}")
        disc = self.discount_input.value() / 100.0
        final = total - (total * disc)
        self.final_amount_label.setText(f"{final:.2f}")
        return total, final

    def update_payment_status_and_balance(self, invoice_id, final_amount):
        conn = _connect()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COALESCE(SUM(amount_paid), 0) FROM payment_history WHERE invoice_id = ?",
            (invoice_id,),
        )
        total_paid = float(cursor.fetchone()[0] or 0.0)

        if not final_amount:
            cursor.execute(
                "SELECT COALESCE(final_amount,0) FROM invoices WHERE invoice_id = ?",
                (invoice_id,),
            )
            final_amount = float((cursor.fetchone() or [0])[0] or 0.0)

        remaining_balance = round(final_amount - total_paid, 2)
        if remaining_balance < 0:
            remaining_balance = 0.0

        payment_status = (
            "Paid" if remaining_balance <= 0 else "Partially Paid" if remaining_balance < final_amount else "Unpaid"
        )

        cursor.execute(
            "UPDATE invoices SET remaining_balance = ?, payment_status = ? WHERE invoice_id = ?",
            (remaining_balance, payment_status, invoice_id),
        )
        conn.commit()
        conn.close()

    def export_to_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "invoices.csv", "CSV Files (*.csv)")
        if not path:
            return
        rows = self.invoice_table.rowCount()
        cols = self.invoice_table.columnCount()
        if rows == 0:
            QMessageBox.warning(self, "No Data", "There are no invoices to export.")
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                headers = [self.invoice_table.horizontalHeaderItem(c).text() for c in range(cols)]
                w.writerow(headers)
                for r in range(rows):
                    w.writerow([self.invoice_table.item(r, c).text() for c in range(cols)])
            QMessageBox.information(self, "Export Successful", f"Invoices exported to {path}.")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"An error occurred while exporting: {e}")

    def clear_invoice_form(self):
        self.appointment_id_input.clear()
        self.patient_name_label.clear()
        self.total_amount_input.clear()
        self.discount_input.setValue(0)
        self.final_amount_label.clear()
        self.remaining_balance_label.clear()
        self.payment_status_dropdown.setCurrentText("Unpaid")
        self.payment_method_dropdown.setCurrentIndex(0)

        self.item_table.setRowCount(0)

        self.save_btn.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.view_payments_button.setEnabled(False)
        self.add_payment_button.setEnabled(False)
        self.print_button.setEnabled(False)
        self.convert_btn.setEnabled(False)

    def clear_inputs(self):
        self.appointment_id_input.clear()
        self.patient_name_label.clear()
        self.total_amount_input.clear()
        self.discount_input.setValue(0)
        self.final_amount_label.clear()
        self.payment_status_dropdown.setCurrentText("Unpaid")
        self.payment_method_dropdown.setCurrentIndex(0)

        self.save_btn.setEnabled(False)
        self.delete_button.setEnabled(False)
