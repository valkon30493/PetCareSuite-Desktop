# consent_forms.py
import os
import sqlite3
from datetime import datetime

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas

from db import connect as _connect

# ---- Clinic Header (edit these) ------------------------------------------------
CLINIC_NAME = "Pet Wellness Vets"
CLINIC_ADDR1 = "Kyriakou Adamou no.2, Shop 2&3, 8220"
CLINIC_ADDR2 = ""
CLINIC_PHONE = "Tel: 99941186"
CLINIC_EMAIL = "Email: contact@petwellnessvets.com"
CLINIC_LOGO = os.path.join(
    os.path.dirname(__file__), "pet_wellness_logo.png"
)  # optional


# ---- Ensure / migrate consent_forms schema -------------------------------------
def _ensure_consent_schema():
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS consent_forms (
            consent_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id     INTEGER NOT NULL REFERENCES patients(patient_id),
            template_id    INTEGER,
            form_type      TEXT,
            body_text      TEXT,
            signed_by      TEXT,
            relation       TEXT,
            follow_up_date TEXT,
            signature_path TEXT,
            status         TEXT NOT NULL DEFAULT 'Draft',
            created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    # Add columns if missing (safe re-run)
    for col, ddl in [
        ("template_id", "INTEGER"),
        ("form_type", "TEXT"),
        ("body_text", "TEXT"),
        ("signed_by", "TEXT"),
        ("relation", "TEXT"),
        ("follow_up_date", "TEXT"),
        ("signature_path", "TEXT"),
        ("status", "TEXT NOT NULL DEFAULT 'Draft'"),
        ("created_at", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"),
    ]:
        try:
            cur.execute(f"ALTER TABLE consent_forms ADD COLUMN {col} {ddl}")
        except sqlite3.OperationalError:
            pass
    # Optional: minimal template table for dropdown (if you already have it, this is harmless)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS consent_templates (
            template_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            body_text   TEXT NOT NULL
        )
    """
    )
    conn.commit()
    conn.close()


_ensure_consent_schema()


class ConsentFormsScreen(QWidget):
    # Allows Patient screen to preselect a patient & open "new consent" quickly
    create_for_patient = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Consent Forms")
        self.selected_consent_id = None
        self.selected_patient_id = None
        self._last_template_id_applied = None  # for smarter replace logic

        main = QVBoxLayout(self)

        # Top row: search/filter
        filters = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by patient or form type…")
        self.search_input.textChanged.connect(self.load_forms)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Draft", "Signed", "Voided"])
        self.status_filter.currentIndexChanged.connect(self.load_forms)
        self.date_from = QDateEdit(QDate.currentDate().addMonths(-1))
        self.date_from.setCalendarPopup(True)
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        for w in (QLabel("From:"), self.date_from, QLabel("To:"), self.date_to):
            filters.addWidget(w)
        self.date_from.dateChanged.connect(self.load_forms)
        self.date_to.dateChanged.connect(self.load_forms)
        filters.addWidget(self.search_input)
        filters.addWidget(QLabel("Status:"))
        filters.addWidget(self.status_filter)
        main.addLayout(filters)

        # Table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Patient",
                "Type",
                "Status",
                "Follow‑up",
                "Signed By",
                "Relation",
                "Created",
            ]
        )
        self.table.itemSelectionChanged.connect(self._on_select)
        main.addWidget(self.table)

        # Form
        form = QFormLayout()
        self.patient_display = QLineEdit()
        self.patient_display.setReadOnly(True)
        self.template_combo = QComboBox()
        self.form_type_in = QLineEdit()
        self.body_text = QTextEdit()
        self.signed_by_in = QLineEdit()
        self.relation_in = QComboBox()
        self.relation_in.addItems(["", "Owner", "Guardian", "Other"])
        self.follow_up_in = QDateEdit()
        self.follow_up_in.setCalendarPopup(True)
        self.follow_up_in.setDate(QDate.currentDate().addDays(7))
        form.addRow("Patient:", self.patient_display)
        form.addRow("Template:", self.template_combo)
        form.addRow("Form Type:", self.form_type_in)
        form.addRow("Body:", self.body_text)
        form.addRow("Signed By:", self.signed_by_in)
        form.addRow("Relation:", self.relation_in)
        form.addRow("Follow‑up Date:", self.follow_up_in)
        main.addLayout(form)

        # Buttons
        btns = QHBoxLayout()
        self.new_btn = QPushButton("New")
        self.save_btn = QPushButton("Save")
        self.sign_btn = QPushButton("Mark as Signed…")
        self.void_btn = QPushButton("Void")
        self.export_btn = QPushButton("Export PDF")
        self.attach_sig = QPushButton("Attach Signature Image")
        for b in (
            self.new_btn,
            self.save_btn,
            self.sign_btn,
            self.void_btn,
            self.attach_sig,
            self.export_btn,
        ):
            btns.addWidget(b)
        main.addLayout(btns)

        # Wire up
        self.new_btn.clicked.connect(self.on_new)
        self.save_btn.clicked.connect(self.on_save)
        self.sign_btn.clicked.connect(self.on_mark_signed)
        self.void_btn.clicked.connect(self.on_void)
        self.export_btn.clicked.connect(self.on_export_pdf)
        self.attach_sig.clicked.connect(self.on_attach_signature)
        self.create_for_patient.connect(self._prefill_for_patient)

        # Seed templates & load
        self._load_templates()
        self.load_forms()
        self.on_new()

    # Public API from Patient screen:
    def quick_create_for(self, patient_id: int, patient_name: str):
        self.create_for_patient.emit(patient_id, patient_name)

    # Internal: called by signal
    def _prefill_for_patient(self, pid: int, pname: str):
        self.selected_patient_id = pid
        self.patient_display.setText(f"{pname} (ID:{pid})")
        self._populate_body_from_template(force=True)

    def _load_templates(self):
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItem("â€â€ None â€â€", None)
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;")
        cur = conn.cursor()
        cur.execute("SELECT template_id, name FROM consent_templates ORDER BY name")
        for tid, name in cur.fetchall():
            self.template_combo.addItem(name, tid)
        conn.close()
        self.template_combo.blockSignals(False)
        # IMPORTANT: connect after filling
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)

    def _on_template_changed(self):
        # Always sync form_type & body to selected template
        self._populate_body_from_template(force=True)

    def _populate_body_from_template(self, force: bool = False):
        tid = self.template_combo.currentData()
        if not tid:
            self._last_template_id_applied = None
            return

        # load patient basics for merge
        owner_name, patient_name, today = "", "", datetime.now().strftime("%Y-%m-%d")
        if self.selected_patient_id:
            conn = _connect()  # autocommit

            conn.execute("PRAGMA foreign_keys=ON;")
            cur = conn.cursor()
            cur.execute(
                "SELECT owner_name, name FROM patients WHERE patient_id=?",
                (self.selected_patient_id,),
            )
            row = cur.fetchone()
            conn.close()
            if row:
                owner_name, patient_name = row

        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;")
        cur = conn.cursor()
        cur.execute(
            "SELECT name, body_text FROM consent_templates WHERE template_id=?", (tid,)
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return
        tpl_name, body = row
        merged = (
            body.replace("{owner_name}", owner_name or "")
            .replace("{patient_name}", patient_name or "")
            .replace("{date}", today)
        )

        # If force or template changed, apply both fields
        if force or self._last_template_id_applied != tid:
            self.form_type_in.setText(tpl_name)
            self.body_text.setPlainText(merged)
            self._last_template_id_applied = tid

    def load_forms(self):
        term = (self.search_input.text() or "").lower()
        status = self.status_filter.currentText()
        d1 = self.date_from.date().toString("yyyy-MM-dd")
        d2 = self.date_to.date().toString("yyyy-MM-dd")
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;")
        cur = conn.cursor()
        q = """
            SELECT c.consent_id, p.name, c.form_type, c.status, c.follow_up_date,
                   c.signed_by, c.relation, c.created_at, p.patient_id
            FROM consent_forms c
            JOIN patients p ON p.patient_id = c.patient_id
            WHERE DATE(c.created_at) BETWEEN DATE(?) AND DATE(?)
        """
        params = [d1, d2]
        if status != "All":
            q += " AND c.status = ?"
            params.append(status)
        cur.execute(q, params)
        rows = cur.fetchall()
        conn.close()

        # Basic keyword filter on patient or form type
        if term:
            rows = [
                r
                for r in rows
                if term in (r[1] or "").lower() or term in (r[2] or "").lower()
            ]

        self.table.setRowCount(0)
        for r, row in enumerate(rows):
            self.table.insertRow(r)
            for c, v in enumerate(row[:8]):  # hide patient_id in table
                self.table.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))

    def _on_select(self):
        r = self.table.currentRow()
        if r < 0:
            return
        cid = int(self.table.item(r, 0).text())
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;")
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.patient_id, p.name, c.form_type, c.body_text, c.signed_by, c.relation,
                   c.status, c.follow_up_date, c.signature_path, c.template_id
            FROM consent_forms c
            JOIN patients p ON p.patient_id=c.patient_id
            WHERE c.consent_id=?
        """,
            (cid,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return
        (pid, pname, ftype, body, signed_by, relation, status, fup, sigpath, tpl_id) = (
            row
        )
        self.selected_consent_id = cid
        self.selected_patient_id = pid
        self.patient_display.setText(f"{pname} (ID:{pid})")
        self.form_type_in.setText(ftype or "")
        self.body_text.setPlainText(body or "")
        self.signed_by_in.setText(signed_by or "")
        self.relation_in.setCurrentText(relation or "")
        if fup:
            # accept yyyy-MM-dd or yyyy-MM-dd HH:MM
            date_str = (fup or "").split(" ")[0]
            self.follow_up_in.setDate(QDate.fromString(date_str, "yyyy-MM-dd"))
        # select template in combo if we can
        if tpl_id is not None:
            idx = self.template_combo.findData(tpl_id)
            if idx >= 0:
                self.template_combo.blockSignals(True)
                self.template_combo.setCurrentIndex(idx)
                self.template_combo.blockSignals(False)
                self._last_template_id_applied = tpl_id
        self.sign_btn.setEnabled(status != "Signed")
        self.void_btn.setEnabled(status != "Voided")

    def on_new(self):
        self.selected_consent_id = None
        # keep selected_patient_id if user came from Patient screen
        self.form_type_in.clear()
        self.body_text.clear()
        self.signed_by_in.clear()
        self.relation_in.setCurrentIndex(0)
        self.follow_up_in.setDate(QDate.currentDate().addDays(7))
        self.template_combo.setCurrentIndex(0)
        self._last_template_id_applied = None
        self.sign_btn.setEnabled(False)
        self.void_btn.setEnabled(False)

    def on_save(self):
        if not self.selected_patient_id:
            QMessageBox.warning(self, "Missing", "Select a patient first.")
            return
        form_type = self.form_type_in.text().strip() or "Consent"
        body = self.body_text.toPlainText().strip()
        if not body:
            QMessageBox.warning(self, "Missing", "Body text is required.")
            return
        fup = self.follow_up_in.date().toString("yyyy-MM-dd")
        tid = self.template_combo.currentData()

        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;")
        cur = conn.cursor()
        if self.selected_consent_id:
            cur.execute(
                """
                UPDATE consent_forms
                   SET template_id=?, form_type=?, body_text=?, follow_up_date=?
                 WHERE consent_id=?
            """,
                (tid, form_type, body, fup, self.selected_consent_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO consent_forms (patient_id, template_id, form_type, body_text, follow_up_date, status)
                VALUES (?,?,?,?,?, 'Draft')
            """,
                (self.selected_patient_id, tid, form_type, body, fup),
            )
            self.selected_consent_id = cur.lastrowid
        conn.commit()
        conn.close()
        self.load_forms()
        QMessageBox.information(self, "Saved", "Consent saved.")

    def on_mark_signed(self):
        if not self.selected_consent_id:
            return
        signer = self.signed_by_in.text().strip()
        if not signer:
            QMessageBox.warning(
                self, "Missing", "Enter 'Signed By' before marking as Signed."
            )
            return
        relation = self.relation_in.currentText()
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;")
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE consent_forms
               SET signed_by=?, relation=?, status='Signed'
             WHERE consent_id=?
        """,
            (signer, relation, self.selected_consent_id),
        )
        conn.commit()
        conn.close()
        self.load_forms()
        QMessageBox.information(self, "Marked", "Consent marked as Signed.")

    def on_void(self):
        if not self.selected_consent_id:
            return
        if QMessageBox.question(self, "Void", "Void this consent?") != QMessageBox.Yes:
            return
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;")
        cur = conn.cursor()
        cur.execute(
            "UPDATE consent_forms SET status='Voided' WHERE consent_id=?",
            (self.selected_consent_id,),
        )
        conn.commit()
        conn.close()
        self.load_forms()

    def on_attach_signature(self):
        """Store a path to a scanned signature image (PNG/JPG)."""
        if not self.selected_consent_id:
            QMessageBox.warning(self, "No Consent", "Save the consent first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach Signature Image", "", "Images (*.png *.jpg *.jpeg)"
        )
        if not path:
            return
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;")
        cur = conn.cursor()
        cur.execute(
            "UPDATE consent_forms SET signature_path=? WHERE consent_id=?",
            (path, self.selected_consent_id),
        )
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Attached", "Signature image attached.")

    def _draw_header(self, pdf, W, H):
        """Draws the clinic header area on the canvas."""
        y = H - 50
        # Logo (left)
        if CLINIC_LOGO and os.path.exists(CLINIC_LOGO):
            try:
                img = ImageReader(CLINIC_LOGO)
                pdf.drawImage(
                    img,
                    50,
                    y - 20,
                    width=80,
                    height=40,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass
        # Text (right)
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawRightString(W - 50, y, CLINIC_NAME)
        pdf.setFont("Helvetica", 10)
        y -= 16
        if CLINIC_ADDR1:
            pdf.drawRightString(W - 50, y, CLINIC_ADDR1)
            y -= 14
        if CLINIC_ADDR2:
            pdf.drawRightString(W - 50, y, CLINIC_ADDR2)
            y -= 14
        contact_line = "  ·  ".join([s for s in (CLINIC_PHONE, CLINIC_EMAIL) if s])
        if contact_line:
            pdf.drawRightString(W - 50, y, contact_line)
        # Separator
        pdf.setStrokeColor(colors.grey)
        pdf.line(50, H - 85, W - 50, H - 85)

    def on_export_pdf(self):
        if not self.selected_consent_id:
            QMessageBox.warning(self, "No Consent", "Select a consent first.")
            return

        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT c.consent_id, p.name, p.owner_name, c.form_type, c.body_text,
                   c.signed_by, c.relation, c.signature_path, c.created_at
            FROM consent_forms c
            JOIN patients p ON p.patient_id=c.patient_id
            WHERE c.consent_id=?
        """,
            (self.selected_consent_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return

        (cid, pet, owner, ftype, body, signed_by, relation, sig_path, created) = row
        default_fn = f"Consent_{cid}_{pet.replace(' ', '')}.pdf"
        out, _ = QFileDialog.getSaveFileName(
            self, "Save PDF", default_fn, "PDF Files (*.pdf)"
        )
        if not out:
            return

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.utils import ImageReader
            from reportlab.pdfgen import canvas as pdf_canvas

            pdf = pdf_canvas.Canvas(out, pagesize=A4)
            W, H = A4

            # --- Clinic Info Header ---
            clinic_name = "Pet Wellness Vets"
            clinic_address = "Kyriakou Adamou no.2, Shop 2&3, 8220"
            clinic_phone = "+357 99 941 186"
            clinic_email = "contact@petwellnessvets.com"
            logo_path = os.path.join(os.path.dirname(__file__), "pet_wellness_logo.png")

            y = H - 40
            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawString(50, y, clinic_name)
            y -= 16
            pdf.setFont("Helvetica", 10)
            pdf.drawString(50, y, clinic_address)
            y -= 12
            pdf.drawString(50, y, clinic_phone)
            y -= 12
            pdf.drawString(50, y, clinic_email)

            # Logo aligned right
            if os.path.exists(logo_path):
                logo = ImageReader(logo_path)
                pdf.drawImage(
                    logo,
                    W - 140,
                    H - 80,
                    width=90,
                    height=60,
                    preserveAspectRatio=True,
                    mask="auto",
                )

            # Divider
            pdf.line(40, H - 100, W - 40, H - 100)
            y = H - 120

            # --- Consent Form Content ---
            pdf.setFont("Helvetica-Bold", 13)
            pdf.drawString(50, y, ftype)
            y -= 25
            pdf.setFont("Helvetica", 10)
            pdf.drawString(50, y, f"Patient: {pet}")
            y -= 14
            pdf.drawString(50, y, f"Owner: {owner}")
            y -= 14
            pdf.drawString(50, y, f"Created: {created}")
            y -= 20

            # Body text (wrapped)
            for line in body.splitlines():
                for chunk in [line[i : i + 95] for i in range(0, len(line), 95)]:
                    pdf.drawString(50, y, chunk)
                    y -= 12
                    if y < 100:
                        pdf.showPage()
                        y = H - 50
                        pdf.setFont("Helvetica", 10)

            y -= 20
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(
                50, y, f"Signed By: {signed_by or ''}    Relation: {relation or ''}"
            )
            y -= 40

            # Signature image
            if sig_path and os.path.exists(sig_path):
                pdf.drawImage(
                    sig_path,
                    50,
                    y - 60,
                    width=200,
                    height=60,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                y -= 70

            pdf.line(50, y, 250, y)
            y -= 12
            pdf.drawString(50, y, "Signature")

            pdf.save()
            QMessageBox.information(self, "Exported", f"Saved to {out}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create PDF:\n{e}")
