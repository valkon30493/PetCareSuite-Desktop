# medical_records.py
import os, sqlite3
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QLineEdit,
    QComboBox, QDateEdit, QTextEdit, QFileDialog, QMessageBox, QSpinBox, QDoubleSpinBox
)
from db import connect as _connect


class MedicalRecordsScreen(QWidget):
    visit_saved = Signal(int)  # emits visit_id

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Medical Records")
        self.selected_patient_id = None
        self.selected_visit_id = None

        main = QVBoxLayout(self)

        # â â  TOP HEADER â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        header_box = QGridLayout()

        self.patient_combo = QComboBox()
        self._load_patients()
        self.on_call_chk = QComboBox(); self.on_call_chk.addItems(["No", "Yes"])
        self.visit_date = QDateEdit(QDate.currentDate()); self.visit_date.setCalendarPopup(True)

        header_box.addWidget(QLabel("Pet:"), 0, 0)
        header_box.addWidget(self.patient_combo, 0, 1)
        header_box.addWidget(QLabel("On-call:"), 0, 2)
        header_box.addWidget(self.on_call_chk, 0, 3)
        header_box.addWidget(QLabel("Visit Date:"), 0, 4)
        header_box.addWidget(self.visit_date, 0, 5)

        # NEW: appointment link
        self.appt_combo = QComboBox()
        self.appt_combo.setPlaceholderText("No linked appointment")
        header_box.addWidget(QLabel("Appointment:"), 0, 6)
        header_box.addWidget(self.appt_combo, 0, 7)

        # Vitals
        self.weight = QDoubleSpinBox(); self.weight.setRange(0, 200); self.weight.setDecimals(2); self.weight.setSuffix(" kg")
        self.temp   = QDoubleSpinBox(); self.temp.setRange(20, 45); self.temp.setDecimals(1); self.temp.setSuffix(" °C")
        self.hr     = QSpinBox(); self.hr.setRange(0, 400); self.hr.setSuffix(" bpm")
        self.rr     = QSpinBox(); self.rr.setRange(0, 200); self.rr.setSuffix(" bpm")

        header_box.addWidget(QLabel("Weight:"), 1, 0); header_box.addWidget(self.weight, 1, 1)
        header_box.addWidget(QLabel("Temperature:"), 1, 2); header_box.addWidget(self.temp, 1, 3)
        header_box.addWidget(QLabel("Heart Rate:"), 1, 4); header_box.addWidget(self.hr, 1, 5)
        header_box.addWidget(QLabel("Resp. Rate:"), 1, 6); header_box.addWidget(self.rr, 1, 7)

        # Quick PE fields
        self.body_score = QComboBox(); self.body_score.addItems(["", "1/9","2/9","3/9","4/9","5/9","6/9","7/9","8/9","9/9"])
        self.mucosa_crt = QComboBox(); self.mucosa_crt.addItems(["", "Pink <2s","Dark/Slow","Pale","Icteric","Cyanotic"])
        self.thorax     = QComboBox(); self.thorax.addItems(["", "Normal","Abnormal"])
        self.lymph      = QComboBox(); self.lymph.addItems(["", "Normal","Enlarged"])
        self.palp_abd   = QComboBox(); self.palp_abd.addItems(["", "Non-painful","Painful","Mass noticed"])
        self.eem        = QComboBox(); self.eem.addItems(["", "Normal","Otitis","Conjunctivitis","Oral Lesions"])
        self.skin       = QComboBox(); self.skin.addItems(["", "Normal","Rash","Alopecia","Erythema"])
        self.repro      = QComboBox(); self.repro.addItems(["", "Normal","Intact","Neutered/Spayed","Findings…"])

        quick_form = QFormLayout()
        quick_form.addRow("Body Scoring:", self.body_score)
        quick_form.addRow("Color of Mucosa / CRT:", self.mucosa_crt)
        quick_form.addRow("Evaluation of Thorax:", self.thorax)
        quick_form.addRow("Peripheral Lymphnodes:", self.lymph)
        quick_form.addRow("Palpation of Abdomen:", self.palp_abd)
        quick_form.addRow("Ears / Eyes / Mouth:", self.eem)
        quick_form.addRow("Skin / Coat:", self.skin)
        quick_form.addRow("Penis/Vulva & Breast:", self.repro)

        header = QHBoxLayout()
        header_left = QWidget(); header_left.setLayout(header_box)
        header.addWidget(header_left, 3)
        header.addLayout(quick_form, 2)
        main.addLayout(header)

        # Quick clinic notes
        self.clinic_notes = QLineEdit()
        self.clinic_notes.setPlaceholderText("Clinic Notes (short)")
        main.addWidget(self.clinic_notes)

        # â â  MIDDLE: list + attachments/notes â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        middle = QHBoxLayout()

        # Left: visit list
        left = QVBoxLayout()
        hl = QHBoxLayout()
        self.new_visit_btn = QPushButton("âž• New Visit")
        self.save_btn      = QPushButton("💾 Save Visit")
        self.del_btn       = QPushButton("🗑 Delete Visit")
        for b in (self.new_visit_btn, self.save_btn, self.del_btn):
            hl.addWidget(b)
        left.addLayout(hl)

        self.visit_table = QTableWidget(0, 4)
        self.visit_table.setHorizontalHeaderLabels(["ID", "Date", "Diagnosis", "Treatment"])
        self.visit_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.visit_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.visit_table.itemSelectionChanged.connect(self._load_selected_visit)
        left.addWidget(self.visit_table, 1)

        # Right: attachments + free notes
        right = QVBoxLayout()
        att_hdr = QHBoxLayout()
        att_hdr.addWidget(QLabel("Attachments"))
        self.add_att_btn = QPushButton("Add…")
        self.open_att_btn= QPushButton("Open")
        self.rem_att_btn = QPushButton("Remove")
        for b in (self.add_att_btn, self.open_att_btn, self.rem_att_btn):
            att_hdr.addWidget(b)
        right.addLayout(att_hdr)

        self.attach_table = QTableWidget(0, 3)
        self.attach_table.setHorizontalHeaderLabels(["ID", "Path", "Note"])
        self.attach_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        right.addWidget(self.attach_table, 1)

        right.addWidget(QLabel("Notes"))
        self.notes_box = QTextEdit()
        right.addWidget(self.notes_box, 1)

        middle.addLayout(left, 3)
        middle.addLayout(right, 2)
        main.addLayout(middle, 3)

        # â â  BOTTOM: workflow areas â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        sections = QGridLayout()
        self.reason_adm = QTextEdit(); self.reason_adm.setPlaceholderText("Reason of Admission…")
        self.tests_proc = QTextEdit(); self.tests_proc.setPlaceholderText("Tests / Procedures…")
        self.findings   = QTextEdit(); self.findings.setPlaceholderText("Findings / Observations…")
        self.diagnosis  = QTextEdit(); self.diagnosis.setPlaceholderText("Diagnosis…")
        self.treatment  = QTextEdit(); self.treatment.setPlaceholderText("Treatment / Medications…")

        sections.addWidget(QLabel("Reason of Admission:"), 0, 0); sections.addWidget(self.reason_adm, 1, 0)
        sections.addWidget(QLabel("Tests / Procedures:"),  0, 1); sections.addWidget(self.tests_proc, 1, 1)
        sections.addWidget(QLabel("Findings:"),            2, 0); sections.addWidget(self.findings,   3, 0)
        sections.addWidget(QLabel("Diagnosis:"),           2, 1); sections.addWidget(self.diagnosis,  3, 1)
        sections.addWidget(QLabel("Treatment:"),           4, 0, 1, 2); sections.addWidget(self.treatment, 5, 0, 1, 2)
        main.addLayout(sections, 4)

        # Wire buttons
        self.patient_combo.currentIndexChanged.connect(self._reload_visit_list)
        self.new_visit_btn.clicked.connect(self._clear_form_for_new)
        self.save_btn.clicked.connect(self._save_visit)
        self.del_btn.clicked.connect(self._delete_visit)
        self.add_att_btn.clicked.connect(self._add_attachment)
        self.open_att_btn.clicked.connect(self._open_attachment)
        self.rem_att_btn.clicked.connect(self._remove_attachment)

        # Initial load
        if self.patient_combo.count():
            self._reload_visit_list()

    # â â  Helpers â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    def _load_patients(self):
        self.patient_combo.clear()
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;"); cur = conn.cursor()
        cur.execute("SELECT patient_id, name FROM patients ORDER BY name COLLATE NOCASE")
        for pid, name in cur.fetchall():
            self.patient_combo.addItem(f"{name} (ID:{pid})", pid)
        conn.close()

    def _load_patient_appointments(self, patient_id):
        """Populate appt combo with this patient's recent + upcoming appointments."""
        self.appt_combo.clear()
        self.appt_combo.addItem("â€â€ No link â€â€", None)
        if not patient_id:
            return
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;"); cur = conn.cursor()
        cur.execute("""
            SELECT appointment_id, COALESCE(date_time,''), COALESCE(veterinarian,''), COALESCE(reason,'')
            FROM appointments
            WHERE patient_id = ?
              AND date(date_time) >= date('now', '-60 days')
            ORDER BY datetime(date_time) DESC
        """, (patient_id,))
        for appt_id, dt, vet, reason in cur.fetchall():
            label = f"#{appt_id} ̢ۢ {dt} ̢ۢ {vet} ̢ۢ {reason}"
            self.appt_combo.addItem(label, appt_id)
        conn.close()

    def _current_patient_id(self):
        return self.patient_combo.currentData()

    def _reload_visit_list(self):
        pid = self._current_patient_id()
        self.visit_table.setRowCount(0)
        # refresh appointments combo for patient
        self._load_patient_appointments(pid)
        if not pid:
            return
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;"); cur = conn.cursor()
        cur.execute("""
            SELECT visit_id, visit_date,
                   COALESCE(NULLIF(TRIM(diagnosis),''), '-'),
                   COALESCE(NULLIF(TRIM(treatment),''), '-')
              FROM visits
             WHERE patient_id = ?
             ORDER BY date(visit_date) DESC, visit_id DESC
        """, (pid,))
        rows = cur.fetchall(); conn.close()

        for r, row in enumerate(rows):
            self.visit_table.insertRow(r)
            for c, v in enumerate(row):
                self.visit_table.setItem(r, c, QTableWidgetItem(str(v)))

        self.selected_visit_id = None
        self._clear_form_for_new(reset_patient=False)

    def _load_selected_visit(self):
        r = self.visit_table.currentRow()
        if r < 0:
            return
        vid = int(self.visit_table.item(r, 0).text())
        self.selected_visit_id = vid

        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;"); cur = conn.cursor()
        cur.execute("""
            SELECT appointment_id, visit_date, on_call, weight_kg, body_score, temperature_c, heart_rate_bpm, resp_rate_bpm,
                   mucosa_crt, thorax_eval, lymph_nodes, palpation_abdomen, ears_eyes_mouth, skin_coat, reproductive,
                   clinic_notes, reason_admission, tests_procedures, findings, diagnosis, treatment, notes
              FROM visits WHERE visit_id = ?
        """, (vid,))
        row = cur.fetchone()

        cur.execute("SELECT attach_id, file_path, COALESCE(note,'') FROM visit_attachments WHERE visit_id=? ORDER BY added_at DESC", (vid,))
        atts = cur.fetchall(); conn.close()

        if not row:
            return

        (appt_id, vdate, oncall, w, bs, t, hr, rr,
         muc, thx, lym, abd, eem, skin, repro,
         cnotes, rofa, tp, fnd, dx, trt, nts) = row

        self.visit_date.setDate(QDate.fromString(vdate, "yyyy-MM-dd"))
        self.on_call_chk.setCurrentText("Yes" if oncall else "No")
        self.weight.setValue(float(w or 0)); self.temp.setValue(float(t or 0))
        self.hr.setValue(int(hr or 0)); self.rr.setValue(int(rr or 0))
        self.body_score.setCurrentText(bs or "")
        self.mucosa_crt.setCurrentText(muc or ""); self.thorax.setCurrentText(thx or "")
        self.lymph.setCurrentText(lym or ""); self.palp_abd.setCurrentText(abd or "")
        self.eem.setCurrentText(eem or ""); self.skin.setCurrentText(skin or "")
        self.repro.setCurrentText(repro or "")
        self.clinic_notes.setText(cnotes or "")
        self.reason_adm.setPlainText(rofa or ""); self.tests_proc.setPlainText(tp or "")
        self.findings.setPlainText(fnd or ""); self.diagnosis.setPlainText(dx or "")
        self.treatment.setPlainText(trt or ""); self.notes_box.setPlainText(nts or "")

        # reset appt list and pick current appt
        self._load_patient_appointments(self._current_patient_id())
        idx = self.appt_combo.findData(appt_id)
        if idx >= 0:
            self.appt_combo.setCurrentIndex(idx)
        elif appt_id:
            self.appt_combo.addItem(f"#{appt_id} (archived)", appt_id)
            self.appt_combo.setCurrentIndex(self.appt_combo.count()-1)

        self.attach_table.setRowCount(0)
        for r, a in enumerate(atts):
            self.attach_table.insertRow(r)
            for c, v in enumerate(a):
                self.attach_table.setItem(r, c, QTableWidgetItem(str(v)))

    def _collect_payload(self):
        return dict(
            patient_id=self._current_patient_id(),
            appointment_id=self.appt_combo.currentData(),
            visit_date=self.visit_date.date().toString("yyyy-MM-dd"),
            on_call=1 if self.on_call_chk.currentText()=="Yes" else 0,
            weight=self.weight.value(),
            body_score=self.body_score.currentText() or None,
            temp=self.temp.value(),
            hr=self.hr.value(),
            rr=self.rr.value(),
            mucosa=self.mucosa_crt.currentText() or None,
            thorax=self.thorax.currentText() or None,
            lymph=self.lymph.currentText() or None,
            abd=self.palp_abd.currentText() or None,
            eem=self.eem.currentText() or None,
            skin=self.skin.currentText() or None,
            repro=self.repro.currentText() or None,
            cnotes=self.clinic_notes.text().strip() or None,
            rofa=self.reason_adm.toPlainText().strip() or None,
            tests=self.tests_proc.toPlainText().strip() or None,
            fnd=self.findings.toPlainText().strip() or None,
            dx=self.diagnosis.toPlainText().strip() or None,
            trt=self.treatment.toPlainText().strip() or None,
            nts=self.notes_box.toPlainText().strip() or None
        )

    # â â  Actions â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    def _save_visit(self):
        data = self._collect_payload()
        if not data["patient_id"]:
            QMessageBox.warning(self, "Missing", "Select a pet first.")
            return

        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;"); cur = conn.cursor()

        if self.selected_visit_id:
            cur.execute("""
                UPDATE visits SET
                  patient_id=?, appointment_id=?, visit_date=?, on_call=?,
                  weight_kg=?, body_score=?, temperature_c=?, heart_rate_bpm=?, resp_rate_bpm=?,
                  mucosa_crt=?, thorax_eval=?, lymph_nodes=?, palpation_abdomen=?, ears_eyes_mouth=?,
                  skin_coat=?, reproductive=?, clinic_notes=?,
                  reason_admission=?, tests_procedures=?, findings=?, diagnosis=?, treatment=?, notes=?
                WHERE visit_id=?
            """, (data["patient_id"], data["appointment_id"], data["visit_date"], data["on_call"],
                  data["weight"], data["body_score"], data["temp"], data["hr"], data["rr"],
                  data["mucosa"], data["thorax"], data["lymph"], data["abd"], data["eem"],
                  data["skin"], data["repro"], data["cnotes"],
                  data["rofa"], data["tests"], data["fnd"], data["dx"], data["trt"], data["nts"],
                  self.selected_visit_id))
            vid = self.selected_visit_id
        else:
            cur.execute("""
                INSERT INTO visits
                    (patient_id, appointment_id, visit_date, on_call,
                     weight_kg, body_score, temperature_c, heart_rate_bpm, resp_rate_bpm,
                     mucosa_crt, thorax_eval, lymph_nodes, palpation_abdomen, ears_eyes_mouth,
                     skin_coat, reproductive, clinic_notes,
                     reason_admission, tests_procedures, findings, diagnosis, treatment, notes)
                VALUES (?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?, ?,?,?, ?,?)
            """, (data["patient_id"], data["appointment_id"], data["visit_date"], data["on_call"],
                  data["weight"], data["body_score"], data["temp"], data["hr"], data["rr"],
                  data["mucosa"], data["thorax"], data["lymph"], data["abd"], data["eem"],
                  data["skin"], data["repro"], data["cnotes"],
                  data["rofa"], data["tests"], data["fnd"], data["dx"], data["trt"], data["nts"]))
            vid = cur.lastrowid
            self.selected_visit_id = vid

        conn.commit(); conn.close()

        # Optional: auto-complete appointment if linked
        # self._mark_appointment_completed_if_needed(data["appointment_id"])

        self._reload_visit_list()
        self.visit_saved.emit(vid)
        QMessageBox.information(self, "Saved", f"Visit #{vid} saved.")

    def _delete_visit(self):
        if not self.selected_visit_id:
            QMessageBox.warning(self, "No selection", "Pick a visit in the table first.")
            return
        if QMessageBox.question(self, "Confirm", "Delete this visit?") != QMessageBox.Yes:
            return
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;"); cur = conn.cursor()
        cur.execute("DELETE FROM visits WHERE visit_id=?", (self.selected_visit_id,))
        conn.commit(); conn.close()
        self.selected_visit_id = None
        self._reload_visit_list()

    def _add_attachment(self):
        if not self.selected_visit_id:
            QMessageBox.warning(self, "No visit", "Save the visit first, then attach files.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Add Attachment")
        if not path:
            return
        note = os.path.basename(path)
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;"); cur = conn.cursor()
        cur.execute("INSERT INTO visit_attachments (visit_id, file_path, note) VALUES (?,?,?)",
                    (self.selected_visit_id, path, note))
        conn.commit(); conn.close()
        self._load_selected_visit()

    def _open_attachment(self):
        r = self.attach_table.currentRow()
        if r < 0: return
        path = self.attach_table.item(r, 1).text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Missing file", "File not found on disk.")
            return
        os.startfile(path) if os.name == "nt" else os.system(f"open '{path}'")

    def _remove_attachment(self):
        r = self.attach_table.currentRow()
        if r < 0: return
        if QMessageBox.question(self, "Remove", "Remove selected attachment?") != QMessageBox.Yes:
            return
        attach_id = int(self.attach_table.item(r, 0).text())
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;"); cur = conn.cursor()
        cur.execute("DELETE FROM visit_attachments WHERE attach_id=?", (attach_id,))
        conn.commit(); conn.close()
        self._load_selected_visit()

    def _clear_form_for_new(self, reset_patient=True):
        if reset_patient and self.patient_combo.count():
            self.patient_combo.setCurrentIndex(0)
        self.selected_visit_id = None
        self.visit_date.setDate(QDate.currentDate())
        self.on_call_chk.setCurrentIndex(0)
        self.weight.setValue(0); self.temp.setValue(0); self.hr.setValue(0); self.rr.setValue(0)
        for cb in (self.body_score, self.mucosa_crt, self.thorax, self.lymph, self.palp_abd, self.eem, self.skin, self.repro):
            cb.setCurrentIndex(0)
        self.clinic_notes.clear()
        for te in (self.reason_adm, self.tests_proc, self.findings, self.diagnosis, self.treatment, self.notes_box):
            te.clear()
        self.attach_table.setRowCount(0)

    # Optional: mark appointment Completed when saving a linked visit
    def _mark_appointment_completed_if_needed(self, appt_id):
        if not appt_id:
            return
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;"); cur = conn.cursor()
        cur.execute("SELECT status FROM appointments WHERE appointment_id=?", (appt_id,))
        row = cur.fetchone()
        if row and row[0] != "Completed":
            cur.execute("UPDATE appointments SET status='Completed' WHERE appointment_id=?", (appt_id,))
            conn.commit()
        conn.close()

    # Public helpers for MainWindow / other screens
    def focus_on_patient(self, patient_id: int, patient_name: str = ""):
        for i in range(self.patient_combo.count()):
            if self.patient_combo.itemData(i) == patient_id:
                self.patient_combo.setCurrentIndex(i)
                break
        self._reload_visit_list()

    def focus_on_visit(self, visit_id: int):
        conn = _connect()  # autocommit

        conn.execute("PRAGMA foreign_keys=ON;"); cur = conn.cursor()
        cur.execute("SELECT patient_id FROM visits WHERE visit_id=?", (visit_id,))
        row = cur.fetchone(); conn.close()
        if not row:
            QMessageBox.warning(self, "Not found", f"Visit #{visit_id} not found.")
            return
        patient_id = row[0]
        self.focus_on_patient(patient_id)
        for r in range(self.visit_table.rowCount()):
            if int(self.visit_table.item(r, 0).text()) == visit_id:
                self.visit_table.selectRow(r)
                self._load_selected_visit()
                break




