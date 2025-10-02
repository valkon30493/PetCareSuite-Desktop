import os
import sqlite3
from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QSpinBox,
                               QTimeEdit, QVBoxLayout)

from db import connect as _connect


class ConsentDialog(QDialog):
    """
    Create & save a consent for a patient, with optional follow‑up appointment
    and an automatic reminder.
    """
    def __init__(self, patient_id: int, patient_name: str, parent=None):
        super().__init__(parent)


        self.patient_id = patient_id
        self.patient_name = patient_name
        self.attachment_path = None

        self.setWindowTitle(f"Create Consent – {patient_name} (ID: {patient_id})")

        main = QVBoxLayout(self)

        # â€â€Ã¢€â€Ã¢€â€ Consent form â€â€Ã¢€â€Ã¢€â€
        form = QFormLayout()

        self.consent_type = QComboBox()
        self.consent_type.addItems([
            "General Treatment Consent",
            "Surgery Consent",
            "Anesthesia Consent",
            "Hospitalization Consent",
            "Medication Consent",
            "Other"
        ])

        self.notes = QPlainTextEdit()
        self.signer_name = QLineEdit()
        self.valid_until = QDateEdit(QDate.currentDate().addYears(1))
        self.valid_until.setCalendarPopup(True)
        self.valid_until.setDisplayFormat("yyyy-MM-dd")

        attach_row = QHBoxLayout()
        self.file_label = QLabel("No file selected")
        attach_btn = QPushButton("Attach PDF/Image…")
        attach_btn.clicked.connect(self.pick_file)
        attach_row.addWidget(self.file_label)
        attach_row.addWidget(attach_btn)

        form.addRow("Consent Type:", self.consent_type)
        form.addRow("Signer Name:", self.signer_name)
        form.addRow("Notes:", self.notes)
        form.addRow("Valid Until:", self.valid_until)
        form.addRow("Attachment:", attach_row)

        main.addLayout(form)

        # â€â€Ã¢€â€Ã¢€â€ Follow‑up (optional) â€â€Ã¢€â€Ã¢€â€
        self.followup_group = QVBoxLayout()
        self.create_followup = QCheckBox("Also create a follow‑up appointment")
        self.create_followup.stateChanged.connect(self._toggle_followup_enabled)
        self.followup_group.addWidget(self.create_followup)

        fu_form = QFormLayout()
        self.fu_date = QDateEdit(QDate.currentDate().addDays(14))
        self.fu_date.setCalendarPopup(True)
        self.fu_date.setDisplayFormat("yyyy-MM-dd")

        self.fu_time = QTimeEdit(QTime.currentTime())
        self.fu_duration = QComboBox()
        self.fu_duration.addItems(["15", "30", "45", "60"])
        self.fu_duration.setCurrentText("30")

        self.fu_reason = QLineEdit("Post‑procedure check")
        self.fu_type = QComboBox()
        self.fu_type.addItems(["Follow-Up", "Examination", "Consultation"])

        self.fu_vet = QComboBox()
        # Match your existing vets in appointment_scheduling.py
        self.fu_vet.addItems(["Dr. Souzana", "Dr. Klio"])

        fu_form.addRow("Date:", self.fu_date)
        fu_form.addRow("Time:", self.fu_time)
        fu_form.addRow("Duration (min):", self.fu_duration)
        fu_form.addRow("Type:", self.fu_type)
        fu_form.addRow("Reason:", self.fu_reason)
        fu_form.addRow("Veterinarian:", self.fu_vet)

        self.followup_group.addLayout(fu_form)
        main.addLayout(self.followup_group)
        self._toggle_followup_enabled()  # default off

        # â€â€Ã¢€â€Ã¢€â€ Reminder (optional, tied to follow‑up) â€â€Ã¢€â€Ã¢€â€
        self.create_reminder = QCheckBox("Create an email reminder for the follow‑up")
        self.reminder_offset = QSpinBox()
        self.reminder_offset.setRange(0, 60 * 24 * 30)
        self.reminder_offset.setValue(24)  # hours before
        self.reminder_offset.setSuffix(" h before")
        rem_row = QHBoxLayout()
        rem_row.addWidget(self.create_reminder)
        rem_row.addStretch(1)
        rem_row.addWidget(self.reminder_offset)
        main.addLayout(rem_row)

        # â€â€Ã¢€â€Ã¢€â€ Buttons â€â€Ã¢€â€Ã¢€â€
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.on_save)
        btns.rejected.connect(self.reject)
        main.addWidget(btns)

    # ----------------- UI helpers -----------------

    def pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach Consent File", "", "PDF or Images (*.pdf *.png *.jpg *.jpeg *.webp)"
        )
        if path:
            self.attachment_path = path
            base = os.path.basename(path)
            self.file_label.setText(base)

    def _toggle_followup_enabled(self):
        enabled = self.create_followup.isChecked()
        for w in (self.fu_date, self.fu_time, self.fu_duration, self.fu_reason, self.fu_type, self.fu_vet,
                  self.create_reminder, self.reminder_offset):
            w.setEnabled(enabled)

    # ----------------- Save logic -----------------

    def on_save(self):
        # 1) Validate minimal consent inputs
        ctype = self.consent_type.currentText().strip()
        signer = self.signer_name.text().strip()

        if not ctype:
            QMessageBox.warning(self, "Missing Data", "Please select a consent type.")
            return
        if not signer:
            QMessageBox.warning(self, "Missing Data", "Please enter the signerâ€â"¢s name.")
            return

        # 2) Insert consent
        try:
            conn = _connect()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO consents (patient_id, consent_type, notes, signer_name, valid_until, file_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                self.patient_id,
                ctype,
                self.notes.toPlainText().strip() or None,
                signer,
                self.valid_until.date().toString("yyyy-MM-dd"),
                self.attachment_path
            ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            conn.close()
            QMessageBox.critical(self, "Error", f"Could not save consent:\n{e}")
            return

        # 3) Optional follow‑up + reminder
        if self.create_followup.isChecked():
            try:
                appt_id = self._create_followup_appointment(cur)
                conn.commit()
                if self.create_reminder.isChecked() and appt_id:
                    self._create_followup_reminder(cur, appt_id)
                    conn.commit()
            except Exception as e:
                conn.rollback()
                conn.close()
                QMessageBox.critical(self, "Error", f"Follow‑up creation failed:\n{e}")
                return

        conn.close()
        QMessageBox.information(self, "Saved", "Consent saved successfully.")
        self.accept()

    def _create_followup_appointment(self, cur) -> int | None:
        """Insert a non‑conflicting follow‑up appointment. Returns appointment_id."""
        # Build start/end based on UI
        start_dt = f"{self.fu_date.date().toString('yyyy-MM-dd')} {self.fu_time.time().toString('HH:mm')}"
        duration = int(self.fu_duration.currentText())
        dt_start = datetime.strptime(start_dt, "%Y-%m-%d %H:%M")
        dt_end = dt_start + timedelta(minutes=duration)
        end_dt = dt_end.strftime("%Y-%m-%d %H:%M")

        vet = self.fu_vet.currentText()
        reason = self.fu_reason.text().strip() or "Follow‑up"
        appt_type = self.fu_type.currentText()

        # Resolve patient_id -> ensure exists (not strictly necessary here)
        # Check conflicts (same logic style as appointment_scheduling.py)
        cur.execute("""
            SELECT COUNT(*)
              FROM appointments
             WHERE veterinarian = ?
               AND datetime(date_time, '+' || duration_minutes || ' minutes') > ?
               AND date_time < ?
        """, (vet, start_dt, end_dt))
        (conflicts,) = cur.fetchone()
        if conflicts:
            raise RuntimeError(f"{vet} has a conflicting appointment between {start_dt} and {end_dt}.")

        # Insert
        cur.execute("""
            INSERT INTO appointments
              (patient_id, date_time, duration_minutes,
               appointment_type, reason, veterinarian, status, notification_status)
            VALUES (?, ?, ?, ?, ?, ?, 'Scheduled', 'Not Sent')
        """, (self.patient_id, start_dt, duration, appt_type, reason, vet))
        return cur.lastrowid

    def _create_followup_reminder(self, cur, appointment_id: int):
        """Insert reminder X hours before the follow‑up appointment."""
        # Fetch appointment datetime
        cur.execute("SELECT date_time FROM appointments WHERE appointment_id = ?", (appointment_id,))
        row = cur.fetchone()
        if not row:
            return
        appt_dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M")
        hours_before = int(self.reminder_offset.value())
        reminder_at = appt_dt - timedelta(hours=hours_before)

        cur.execute("""
            INSERT INTO reminders (appointment_id, reminder_time, reminder_status, reminder_reason)
            VALUES (?, ?, 'Pending', ?)
        """, (appointment_id, reminder_at.strftime("%Y-%m-%d %H:%M:%S"),
              f"Follow‑up for {self.patient_name}"))



