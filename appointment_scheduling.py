import sqlite3
import csv
from datetime import datetime, timedelta
from db import connect as get_conn
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QTableWidget, QTableWidgetItem,
    QLineEdit, QComboBox, QPushButton, QMessageBox, QCompleter, QDateEdit, QLabel,
    QFileDialog, QCalendarWidget, QTimeEdit, QDialog, QDateTimeEdit, QHeaderView,
    QCheckBox
)
from PySide6.QtCore import Qt, QDate, QStringListModel, QTime, Signal, QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QBrush, QPalette, QGuiApplication
from notifications import send_email
from logger import log_error




# â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
# Enhanced Multi‑Select Calendar
# - Allows selecting *past* dates
# - Obvious blue highlight for selected dates
# - Shift‑click to select continuous ranges
# - Public helpers to clear/apply selection from outside
# â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
class MultiSelectCalendar(QCalendarWidget):
    def __init__(self):
        super().__init__()

        # Use a string key ("yyyy-MM-dd") so it's definitely hashable/cross-page safe
        self._selected_keys: set[str] = set()
        self._last_clicked: QDate | None = None

        # Calendar appearance
        self.setGridVisible(True)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.ISOWeekNumbers)
        # IMPORTANT: allow past dates
        # (We *remove* the minimum date restriction so staff can back-fill/adjust.)
        # self.setMinimumDate(QDate.currentDate())  # ↠removed by request

        # Prepare a vivid "selected" format (blue background, white text)
        self._sel_fmt = QTextCharFormat()
        # Use system highlight color if available; otherwise fallback
        pal: QPalette = self.palette()
        sel_color: QColor = pal.color(QPalette.Highlight) if pal.isCopyOf(pal) is False else QColor("#1976d2")
        self._sel_fmt.setBackground(QBrush(sel_color))
        self._sel_fmt.setForeground(QBrush(QColor("white")))
        self._sel_fmt.setFontWeight(600)

        # Signals
        self.clicked.connect(self._on_clicked)
        self.currentPageChanged.connect(lambda *_: self._reapply_formats())

    # â â  Selection helpers â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    def _key(self, d: QDate) -> str:
        return d.toString("yyyy-MM-dd")

    def _apply(self, d: QDate, selected: bool):
        # Apply or clear the visual selection style
        self.setDateTextFormat(d, self._sel_fmt if selected else QTextCharFormat())

    def _reapply_formats(self):
        # Re-paint all selected days (useful when month page changes)
        for key in list(self._selected_keys):
            d = QDate.fromString(key, "yyyy-MM-dd")
            self._apply(d, True)

    def clear_selection(self):
        for key in list(self._selected_keys):
            d = QDate.fromString(key, "yyyy-MM-dd")
            self._apply(d, False)
        self._selected_keys.clear()
        self._last_clicked = None

    def set_single_date(self, d: QDate):
        self.clear_selection()
        self._selected_keys.add(self._key(d))
        self._apply(d, True)
        self._last_clicked = d

    def set_selected_dates(self, dates: list[QDate]):
        self.clear_selection()
        for d in dates:
            self._selected_keys.add(self._key(d))
            self._apply(d, True)
        self._last_clicked = dates[-1] if dates else None

    def get_selected_dates(self) -> list[QDate]:
        return sorted([QDate.fromString(k, "yyyy-MM-dd") for k in self._selected_keys])

    # â â  Event handlers â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    def _on_clicked(self, d: QDate):
        # Use the real keyboard modifiers from the application
        modifiers = QGuiApplication.keyboardModifiers()

        if (modifiers & Qt.ShiftModifier) and self._last_clicked:
            # Range select between last clicked and current
            start, end = sorted([self._last_clicked, d])
            cursor = QDate(start)
            while cursor <= end:
                key = self._key(cursor)
                if key not in self._selected_keys:
                    self._selected_keys.add(key)
                    self._apply(cursor, True)
                cursor = cursor.addDays(1)
        else:
            # Toggle single date
            key = self._key(d)
            if key in self._selected_keys:
                self._selected_keys.remove(key)
                self._apply(d, False)
            else:
                self._selected_keys.add(key)
                self._apply(d, True)
            self._last_clicked = d


# â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
# Appointment Scheduling Screen
# â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
class AppointmentSchedulingScreen(QWidget):
    reminders_list_updated = Signal()
    navigate_to_billing_signal = Signal(int)
    # Emitted when the UI asks to open the Visit screen for the selected appointment
    # Payload: appointment_id (int)
    open_visit_requested = Signal(int)

    def __init__(self):
        super().__init__()

        self.selected_appointment_id: int | None = None

        # Periodic notification check (every minute)
        self.notification_timer = QTimer(self)
        self.notification_timer.timeout.connect(self.check_and_send_notifications)
        self.notification_timer.start(60_000)

        # â â  Layouts â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        layout = QVBoxLayout(self)

        # â â  Search row â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        search_layout = QHBoxLayout()
        self.search_patient_name_input = QLineEdit()
        self.search_patient_name_input.setPlaceholderText("Search by Patient Name")
        search_layout.addWidget(QLabel("Patient Name:"))
        search_layout.addWidget(self.search_patient_name_input)

        self.search_appointment_id_input = QLineEdit()
        self.search_appointment_id_input.setPlaceholderText("Search by Appointment ID")
        search_layout.addWidget(QLabel("Appointment ID:"))
        search_layout.addWidget(self.search_appointment_id_input)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.search_appointments)
        search_layout.addWidget(self.search_button)

        self.clear_search_button = QPushButton("Clear")
        self.clear_search_button.clicked.connect(self.load_appointments)
        search_layout.addWidget(self.clear_search_button)

        layout.addLayout(search_layout)

        # â â  Form â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        form_layout = QFormLayout()

        # Patient
        self.patient_input = QLineEdit()
        self.patient_input.setPlaceholderText("Search for a patient…")
        self.patient_completer = QCompleter()
        self.patient_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.patient_input.setCompleter(self.patient_completer)
        self.patient_input.textChanged.connect(self.filter_patients)
        form_layout.addRow("Patient:", self.patient_input)

        # Calendar + helpers
        self.multi_calendar = MultiSelectCalendar()
        self.allow_past_chk = QCheckBox("Allow past dates")
        self.allow_past_chk.setChecked(True)  # default per clinic request
        self.allow_past_chk.toggled.connect(self._toggle_past_dates)

        cal_box = QVBoxLayout()
        cal_box.addWidget(self.multi_calendar)
        cal_box.addWidget(self.allow_past_chk)
        form_layout.addRow("Select Dates:", self._wrap(cal_box))

        # Time & duration
        self.time_picker = QTimeEdit(); self.time_picker.setTime(QTime.currentTime())
        form_layout.addRow("Time:", self.time_picker)

        self.duration_dropdown = QComboBox(); self.duration_dropdown.addItems(["15","30","45","60"])
        self.duration_dropdown.setCurrentText("30")
        form_layout.addRow("Duration (min):", self.duration_dropdown)

        # Type/Reason/Vet/Status
        self.type_dropdown = QComboBox(); self.type_dropdown.addItems(["General","Examination","Consultation","Follow-Up","Surgery"])
        form_layout.addRow("Appointment Type:", self.type_dropdown)

        self.reason_input = QLineEdit(); self.reason_input.setPlaceholderText("Reason for Visit")
        form_layout.addRow("Reason:", self.reason_input)

        self.vet_dropdown = QComboBox(); self.vet_dropdown.addItem("Select Veterinarian"); self.vet_dropdown.addItems(["Dr. Souzana","Dr. Klio"])  # sample
        form_layout.addRow("Veterinarian:", self.vet_dropdown)

        self.status_dropdown = QComboBox(); self.status_dropdown.addItems(["Scheduled","To be Confirmed","Completed","No-show","Canceled"])
        form_layout.addRow("Status:", self.status_dropdown)

        layout.addLayout(form_layout)

        # â â  Filters â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        filter_layout = QHBoxLayout()
        self.start_date_filter = QDateEdit(); self.start_date_filter.setCalendarPopup(True); self.start_date_filter.setDate(QDate.currentDate().addMonths(-1))
        self.end_date_filter   = QDateEdit(); self.end_date_filter.setCalendarPopup(True);   self.end_date_filter.setDate(QDate.currentDate())
        filter_layout.addWidget(QLabel("Start Date:")); filter_layout.addWidget(self.start_date_filter)
        filter_layout.addWidget(QLabel("End Date:"));   filter_layout.addWidget(self.end_date_filter)

        self.status_filter = QComboBox(); self.status_filter.addItem("All"); self.status_filter.addItems(["Scheduled","To be Confirmed","Completed","No-show","Canceled"])
        filter_layout.addWidget(QLabel("Status:")); filter_layout.addWidget(self.status_filter)

        apply_btn = QPushButton("Apply Filters"); apply_btn.clicked.connect(self.apply_filters)
        filter_layout.addWidget(apply_btn)
        layout.addLayout(filter_layout)

        # â â  Action buttons â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        btns = QHBoxLayout()
        self.schedule_button = QPushButton("Schedule Appointment"); self.schedule_button.clicked.connect(self.schedule_appointment)
        self.edit_button     = QPushButton("Edit Appointment");     self.edit_button.setEnabled(False); self.edit_button.clicked.connect(self.edit_appointment)
        self.complete_button = QPushButton("Mark as Completed");    self.complete_button.setEnabled(False); self.complete_button.clicked.connect(self.mark_as_completed)
        self.create_invoice_button = QPushButton("Create Invoice"); self.create_invoice_button.setEnabled(False); self.create_invoice_button.clicked.connect(self.navigate_to_billing)
        self.cancel_button   = QPushButton("Cancel Appointment");   self.cancel_button.setEnabled(False); self.cancel_button.clicked.connect(self.cancel_appointment)
        self.reminder_button = QPushButton("Set Reminder");         self.reminder_button.setEnabled(False); self.reminder_button.clicked.connect(self.set_reminder)
        self.view_all_button = QPushButton("View All Appointments");self.view_all_button.clicked.connect(self.load_appointments)
        self.export_button   = QPushButton("Export to CSV");        self.export_button.clicked.connect(self.export_to_csv)

        for b in (self.schedule_button, self.edit_button, self.complete_button, self.cancel_button,
                  self.reminder_button, self.view_all_button, self.export_button, self.create_invoice_button):
            btns.addWidget(b)
        layout.addLayout(btns)

        # â â  Appointments table â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        self.appointment_table = QTableWidget()
        self.appointment_table.setColumnCount(8)
        self.appointment_table.setHorizontalHeaderLabels([
            "ID", "Patient", "Date & Time (Dur)", "Type", "Reason", "Veterinarian", "Status", "Notification Status"
        ])
        self.appointment_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.appointment_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.appointment_table.itemSelectionChanged.connect(self.load_selected_appointment)
        self.appointment_table.setSortingEnabled(True)
        layout.addWidget(self.appointment_table)

        # â â  Data/state â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
        self.all_patients: list[tuple[str, str]] = []  # (id, name)
        self.load_patients()
        self.load_appointments()

    # Small helper to embed a layout into a single QWidget row
    def _wrap(self, inner_layout: QVBoxLayout) -> QWidget:
        w = QWidget(); w.setLayout(inner_layout); return w

    def _toggle_past_dates(self, allow: bool):
        if allow:
            self.multi_calendar.setMinimumDate(QDate(1900, 1, 1))
        else:
            self.multi_calendar.setMinimumDate(QDate.currentDate())
        # reapply highlight (Qt sometimes recalculates month cells after min date change)
        self.multi_calendar._reapply_formats()

    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    # Search / Patients
    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    def search_appointments(self):
        patient_name = self.search_patient_name_input.text().strip()
        appointment_id = self.search_appointment_id_input.text().strip()

        query = (
            """
            SELECT a.appointment_id, p.name, a.date_time, a.duration_minutes,
                   a.appointment_type, a.reason, a.veterinarian, a.status, a.notification_status
              FROM appointments a
              JOIN patients p ON a.patient_id = p.patient_id
             WHERE 1=1
            """
        )
        params: list = []
        if patient_name:
            query += " AND p.name LIKE ?"; params.append(f"%{patient_name}%")
        if appointment_id:
            query += " AND a.appointment_id = ?"; params.append(appointment_id)

        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute(query, params); rows = cur.fetchall(); conn.close()
            self._fill_table(rows)
            if not rows:
                QMessageBox.information(self, "No Results", "No appointments found matching the search criteria.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while searching:\n{e}")

    def reload_patients(self):
        self.load_patients()
        QMessageBox.information(self, "Patient List Updated", "The patient list has been updated.")

    def load_patients(self):
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT patient_id, name FROM patients ORDER BY name")
        patients = cur.fetchall(); conn.close()
        self.all_patients = [(str(pid), name) for pid, name in patients]
        model = QStringListModel([f"{name} (ID: {pid})" for pid, name in self.all_patients])
        self.patient_completer.setModel(model)

    def filter_patients(self, text: str):
        filtered = [f"{name} (ID: {pid})" for pid, name in self.all_patients if text.lower() in name.lower()]
        self.patient_completer.setModel(QStringListModel(filtered))

    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    # CRUD
    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    def schedule_appointment(self):
        try:
            patient_text = self.patient_input.text().strip()
            if not patient_text or "(ID:" not in patient_text:
                QMessageBox.warning(self, "Input Error", "Please select a valid patient.")
                return

            patient_id = int(patient_text.split("(ID: ")[1].rstrip(")"))
            dates = self.multi_calendar.get_selected_dates()
            appt_type = self.type_dropdown.currentText()
            reason = self.reason_input.text().strip()
            vet = self.vet_dropdown.currentText()
            status = self.status_dropdown.currentText()
            sel_time = self.time_picker.time().toString("HH:mm")
            duration = int(self.duration_dropdown.currentText())

            if not dates:
                QMessageBox.warning(self, "Input Error", "Please select at least one date.")
                return
            if vet == "Select Veterinarian" or not reason:
                QMessageBox.warning(self, "Input Error", "Please fill out all required fields.")
                return

            conn = get_conn(); cur = conn.cursor()
            count = 0
            for d in dates:
                dt_start_str = f"{d.toString('yyyy-MM-dd')} {sel_time}"
                dt_start = datetime.strptime(dt_start_str, "%Y-%m-%d %H:%M")
                dt_end_str = (dt_start + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M")

                # Conflict check (same vet overlapping)
                cur.execute(
                    """
                    SELECT COUNT(*)
                      FROM appointments
                     WHERE veterinarian = ?
                       AND datetime(date_time, '+' || duration_minutes || ' minutes') > ?
                       AND date_time < ?
                    """,
                    (vet, dt_start_str, dt_end_str)
                )
                (conflict_count,) = cur.fetchone()
                if conflict_count:
                    QMessageBox.warning(self, "Scheduling Conflict",
                                        f"{vet} already booked overlapping {dt_start_str}–{dt_end_str}")
                    continue

                cur.execute(
                    """
                    INSERT INTO appointments
                        (patient_id, date_time, duration_minutes,
                         appointment_type, reason, veterinarian, status, notification_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'Not Sent')
                    """,
                    (patient_id, dt_start_str, duration, appt_type, reason, vet, status)
                )
                count += 1

            conn.commit(); conn.close()
            QMessageBox.information(self, "Success", f"Scheduled {count} new appointment(s).")
            self.load_appointments(); self.clear_inputs()
        except Exception as e:
            log_error(f"Error scheduling appointment: {e}")
            QMessageBox.critical(self, "Error", "Failed to schedule appointment.")

    def edit_appointment(self):
        if not self.selected_appointment_id:
            QMessageBox.warning(self, "No Appointment Selected", "Please select an appointment to edit.")
            return

        # Patient
        patient_text = self.patient_input.text().strip()
        if "(ID:" not in patient_text:
            QMessageBox.warning(self, "Input Error", "Please select a valid patient.")
            return
        patient_id = int(patient_text.split("(ID: ")[1].rstrip(")"))

        # Exactly one date for edit
        dates = self.multi_calendar.get_selected_dates()
        if len(dates) != 1:
            QMessageBox.warning(self, "Input Error", "Please select exactly one date for editing.")
            return
        sel_date = dates[0]

        sel_time = self.time_picker.time().toString("HH:mm")
        date_time = f"{sel_date.toString('yyyy-MM-dd')} {sel_time}"
        duration = int(self.duration_dropdown.currentText())
        appt_type = self.type_dropdown.currentText(); reason = self.reason_input.text().strip()
        vet = self.vet_dropdown.currentText(); status = self.status_dropdown.currentText()
        if vet == "Select Veterinarian" or not reason:
            QMessageBox.warning(self, "Input Error", "Please fill out all required fields.")
            return

        dt_start = datetime.strptime(date_time, "%Y-%m-%d %H:%M")
        dt_end_str = (dt_start + timedelta(minutes=duration)).strftime("%Y-%m-%d %H:%M")

        conn = get_conn(); cur = conn.cursor()
        # Conflict check excluding current appt
        cur.execute(
            """
            SELECT COUNT(*) FROM appointments
             WHERE veterinarian = ? AND appointment_id != ?
               AND datetime(date_time, '+' || duration_minutes || ' minutes') > ?
               AND date_time < ?
            """,
            (vet, self.selected_appointment_id, date_time, dt_end_str)
        )
        (conflicts,) = cur.fetchone()
        if conflicts:
            QMessageBox.warning(self, "Scheduling Conflict",
                                f"{vet} already has an overlapping appointment between {date_time} and {dt_end_str}.")
            conn.close(); return

        # Preserve/reset notification flag
        cur.execute("SELECT notification_status, date_time FROM appointments WHERE appointment_id=?",
                    (self.selected_appointment_id,))
        notif_status, orig_dt = cur.fetchone()
        if orig_dt != date_time:
            notif_status = "Not Sent"

        # Update
        cur.execute(
            """
            UPDATE appointments
               SET patient_id = ?, date_time = ?, duration_minutes = ?,
                   appointment_type = ?, reason = ?, veterinarian = ?,
                   status = ?, notification_status = ?
             WHERE appointment_id = ?
            """,
            (patient_id, date_time, duration, appt_type, reason, vet, status, notif_status, self.selected_appointment_id)
        )
        conn.commit(); conn.close()

        QMessageBox.information(self, "Success", "Appointment updated successfully.")
        self.load_appointments(); self.clear_inputs()

    def mark_as_completed(self):
        if not self.selected_appointment_id:
            QMessageBox.warning(self, "No Appointment Selected", "Please select an appointment to mark as completed.")
            return
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE appointments SET status='Completed' WHERE appointment_id=?", (self.selected_appointment_id,))
        conn.commit(); conn.close()
        QMessageBox.information(self, "Success", "Appointment marked as completed.")
        self.load_appointments(); self.clear_inputs()

    def cancel_appointment(self):
        if not self.selected_appointment_id:
            QMessageBox.warning(self, "No Appointment Selected", "Please select an appointment to cancel.")
            return
        if QMessageBox.question(self, "Cancel Confirmation", "Cancel this appointment?",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE appointments SET status='Canceled' WHERE appointment_id=?", (self.selected_appointment_id,))
        conn.commit(); conn.close()
        QMessageBox.information(self, "Success", "Appointment canceled successfully.")
        self.load_appointments(); self.clear_inputs()

    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    # Billing navigation
    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    def navigate_to_billing(self):
        if not self.selected_appointment_id:
            QMessageBox.warning(self, "No Appointment Selected", "Please select an appointment.")
            return
        self.navigate_to_billing_signal.emit(self.selected_appointment_id)

    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    # Reminder dialog and creation
    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    class ReminderDialog(QDialog):
        def __init__(self, appointment_id: int):
            super().__init__()
            self.setWindowTitle("Set Reminder")
            self.appointment_id = appointment_id

            layout = QVBoxLayout(self)
            self.reminder_time_picker = QDateTimeEdit(); self.reminder_time_picker.setCalendarPopup(True)
            cal = self.reminder_time_picker.calendarWidget(); cal.setGridVisible(True)
            cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.ISOWeekNumbers)
            layout.addWidget(QLabel("Reminder Date & Time:")); layout.addWidget(self.reminder_time_picker)

            self.reason_input = QLineEdit(); self.reason_input.setPlaceholderText("Enter reminder reason (optional)")
            layout.addWidget(QLabel("Reason for Reminder:")); layout.addWidget(self.reason_input)

            save_button = QPushButton("Save Reminder"); save_button.clicked.connect(self.save_reminder)
            layout.addWidget(save_button)

        def save_reminder(self):
            reminder_time = self.reminder_time_picker.dateTime().toString("yyyy-MM-dd HH:mm")
            reason = self.reason_input.text().strip()
            if not reminder_time:
                QMessageBox.warning(self, "Input Error", "Please select a valid reminder time.")
                return
            conn = get_conn(); cur = conn.cursor()
            cur.execute(
                "INSERT INTO reminders (appointment_id, reminder_time, reminder_reason, reminder_status) VALUES (?, ?, ?, 'Pending')",
                (self.appointment_id, reminder_time, reason)
            )
            conn.commit(); conn.close()
            QMessageBox.information(self, "Success", "Reminder set successfully.")
            self.accept()

    def set_reminder(self):
        if not self.selected_appointment_id:
            QMessageBox.warning(self, "No Appointment Selected", "Please select an appointment to set a reminder.")
            return
        dialog = self.ReminderDialog(self.selected_appointment_id); dialog.exec()
        self.reminders_list_updated.emit()

    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    # Export / Load / Filters
    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    def export_to_csv(self):
        default_filename = f"appointments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", default_filename, "CSV Files (*.csv)")
        if not path:
            return
        rows = self.appointment_table.rowCount()
        if rows == 0:
            QMessageBox.warning(self, "No Data", "There are no appointments to export.")
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                headers = [self.appointment_table.horizontalHeaderItem(c).text() for c in range(self.appointment_table.columnCount())]
                w.writerow(headers)
                for r in range(rows):
                    w.writerow([self.appointment_table.item(r, c).text() for c in range(self.appointment_table.columnCount())])
            QMessageBox.information(self, "Export Successful", f"Appointments exported to: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"An error occurred: {e}")

    def load_appointments(self):
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute(
                """
                SELECT a.appointment_id, p.name, a.date_time, a.duration_minutes,
                       a.appointment_type, a.reason, a.veterinarian, a.status, a.notification_status
                  FROM appointments a
                  JOIN patients p ON a.patient_id = p.patient_id
                """
            )
            rows = cur.fetchall(); conn.close()
            self._fill_table(rows)
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"An error occurred while loading appointments:\n{e}")

    def _fill_table(self, rows: list[tuple]):
        self.appointment_table.setRowCount(0)
        for r, row in enumerate(rows):
            appt_id, patient, dt, dur, typ, reason, vet, status, notif = row
            self.appointment_table.insertRow(r)
            self.appointment_table.setItem(r, 0, QTableWidgetItem(str(appt_id)))
            self.appointment_table.setItem(r, 1, QTableWidgetItem(patient))
            self.appointment_table.setItem(r, 2, QTableWidgetItem(f"{dt} ({dur} min)"))
            for c, val in enumerate((typ, reason, vet, status, notif), start=3):
                self.appointment_table.setItem(r, c, QTableWidgetItem(str(val)))

    def apply_filters(self):
        start = self.start_date_filter.date().toString("yyyy-MM-dd") + " 00:00"
        end   = self.end_date_filter.date().toString("yyyy-MM-dd")   + " 23:59"
        status = self.status_filter.currentText()

        query = (
            """
            SELECT a.appointment_id, p.name, a.date_time, a.duration_minutes,
                   a.appointment_type, a.reason, a.veterinarian, a.status, a.notification_status
              FROM appointments a
              JOIN patients p ON a.patient_id = p.patient_id
             WHERE a.date_time BETWEEN ? AND ?
            """
        )
        params = [start, end]
        if status != "All":
            query += " AND a.status = ?"; params.append(status)

        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute(query, params); rows = cur.fetchall(); conn.close()
            self._fill_table(rows)
            if not rows:
                QMessageBox.information(self, "No Results", "No appointments found for those filters.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not apply filters:\n{e}")

    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    # Table selection → form
    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    def load_selected_appointment(self):
        r = self.appointment_table.currentRow()
        if r < 0:
            return
        appt_id = int(self.appointment_table.item(r, 0).text())

        conn = get_conn(); cur = conn.cursor()
        cur.execute(
            """
            SELECT patient_id, date_time, duration_minutes,
                   appointment_type, reason, veterinarian, status
              FROM appointments
             WHERE appointment_id = ?
            """,
            (appt_id,)
        )
        row = cur.fetchone(); conn.close()
        if not row:
            QMessageBox.warning(self, "Error", "Could not load that appointment.")
            return

        patient_id, dt, dur, typ, reason, vet, status = row

        # Patient field
        try:
            name = next(n for pid, n in self.all_patients if pid == str(patient_id))
        except StopIteration:
            name = "(Unknown)"
        self.patient_input.setText(f"{name} (ID: {patient_id})")

        # Calendar selection + time (use helper so the day turns BLUE)
        date_part, time_part = dt.split(" ")
        self.multi_calendar.set_single_date(QDate.fromString(date_part, "yyyy-MM-dd"))
        self.time_picker.setTime(QTime.fromString(time_part, "HH:mm"))

        # Duration & other fields
        self.duration_dropdown.setCurrentText(str(dur))
        self.type_dropdown.setCurrentText(typ)
        self.reason_input.setText(reason)
        self.vet_dropdown.setCurrentText(vet)
        self.status_dropdown.setCurrentText(status)

        # Buttons
        self.schedule_button.setEnabled(False)
        self.edit_button.setEnabled(True)
        self.complete_button.setEnabled(status == "Scheduled")
        self.cancel_button.setEnabled(status not in ("Completed", "Canceled"))
        self.reminder_button.setEnabled(True)
        self.create_invoice_button.setEnabled(True)

        self.selected_appointment_id = appt_id

    # Called when jumping from Patient screen
    def load_patient_details(self, patient_id: int, patient_name: str):
        self.clear_inputs()
        self.patient_input.setText(f"{patient_name} (ID: {patient_id})")
        self.patient_input.setStyleSheet("background-color: lightyellow;")
        QTimer.singleShot(2000, lambda: self.patient_input.setStyleSheet(""))

    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    # Notifications (T‑1 day email)
    # â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â 
    def check_and_send_notifications(self):
        try:
            current_time = datetime.now()
            target_day = (current_time + timedelta(days=1)).strftime("%Y-%m-%d")
            start = f"{target_day} 00:00"; end = f"{target_day} 23:59"

            conn = get_conn(); cur = conn.cursor()
            cur.execute(
                """
                SELECT a.appointment_id, a.date_time, a.reason, a.status,
                       p.owner_email, p.owner_name
                  FROM appointments a
                  JOIN patients p ON a.patient_id = p.patient_id
                 WHERE a.date_time BETWEEN ? AND ?
                   AND a.notification_status = 'Not Sent'
                   AND a.status IN ('Scheduled','To be Confirmed')
                """,
                (start, end)
            )
            rows = cur.fetchall()

            sent_ids = []
            for appt_id, dt_str, reason, status, email, owner_name in rows:
                if not email:
                    continue
                subject = "Appointment Reminder"
                message = (
                    f"Dear {owner_name},\n\n"
                    f"This is a reminder for your pet's appointment on {dt_str}.\n"
                    f"Reason: {reason}\n\n"
                    "See you soon!\nPet Wellness Vets"
                )
                if send_email(email, subject, message):
                    sent_ids.append(appt_id)

            if sent_ids:
                cur.executemany("UPDATE appointments SET notification_status='Sent' WHERE appointment_id=?",
                                [(i,) for i in sent_ids])
                conn.commit()
            conn.close()
        except Exception as e:
            log_error(f"check_and_send_notifications error: {e}")

    def stop_timers(self):
        for t in getattr(self, "owned_timers", []):
            try:
                t.stop();
                t.deleteLater()
            except Exception:
                pass
        # or, if you have single attributes:
        try:
            self.notification_timer.stop(); self.notification_timer.deleteLater()
        except Exception:
            pass

    def clear_inputs(self):
        self.patient_input.clear()
        self.multi_calendar.clear_selection()
        self.time_picker.setTime(QTime.currentTime())
        self.duration_dropdown.setCurrentText("30")
        self.type_dropdown.setCurrentIndex(0)
        self.reason_input.clear()
        self.vet_dropdown.setCurrentIndex(0)
        self.status_dropdown.setCurrentIndex(0)
        self.selected_appointment_id = None
        self.schedule_button.setEnabled(True)
        self.edit_button.setEnabled(False)
        self.complete_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.reminder_button.setEnabled(False)
        self.create_invoice_button.setEnabled(False)




