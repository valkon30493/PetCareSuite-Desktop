from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QCalendarWidget, QLabel)
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtCore import QDate
import sqlite3

from db import connect as _connect

class DailyAppointmentsCalendar(QWidget):
    def __init__(self):
        super().__init__()

        # Main layout
        layout = QVBoxLayout()

        # Calendar widget
        self.calendar = QCalendarWidget()
        self.calendar.clicked.connect(self.show_appointments_for_date)
        layout.addWidget(self.calendar)

        # Label to display the selected date
        self.date_label = QLabel("Appointments for: " + QDate.currentDate().toString("yyyy-MM-dd"))
        layout.addWidget(self.date_label)

        # Table to display appointments for the selected date
        self.appointments_table = QTableWidget()
        self.appointments_table.setColumnCount(5)
        self.appointments_table.setHorizontalHeaderLabels(["Time", "Patient", "Owner", "Reason", "Veterinarian"])
        layout.addWidget(self.appointments_table)

        self.setLayout(layout)

        # Load and highlight appointment dates
        self.load_appointments()

    def load_appointments(self):
        """Fetch all appointment dates and highlight them in the calendar."""
        conn = _connect()
        cursor = conn.cursor()

        # Query to get all appointment dates
        cursor.execute("SELECT DISTINCT DATE(date_time) FROM appointments")
        dates = cursor.fetchall()
        conn.close()

        # Highlight dates with appointments
        calendar_format = QTextCharFormat()
        calendar_format.setForeground(QColor("blue"))
        for date_row in dates:
            date = QDate.fromString(date_row[0], "yyyy-MM-dd")
            self.calendar.setDateTextFormat(date, calendar_format)

        # Show appointments for today by default
        self.show_appointments_for_date(QDate.currentDate())

    def show_appointments_for_date(self, date):
        """Display appointments for the selected date."""
        selected_date = date.toString("yyyy-MM-dd")
        self.date_label.setText(f"Appointments for: {selected_date}")

        conn = _connect()
        cursor = conn.cursor()

        # Query to fetch appointments for the selected date
        cursor.execute('''
            SELECT 
                TIME(date_time) AS time,
                p.name AS patient_name,
                p.owner_name,
                a.reason,
                a.veterinarian
            FROM appointments a
            JOIN patients p ON a.patient_id = p.patient_id
            WHERE DATE(a.date_time) = ?
            ORDER BY a.date_time
        ''', (selected_date,))
        appointments = cursor.fetchall()
        conn.close()

        # Populate the table with appointments
        self.appointments_table.setRowCount(0)
        for row_index, appointment in enumerate(appointments):
            self.appointments_table.insertRow(row_index)
            for col_index, value in enumerate(appointment):
                self.appointments_table.setItem(row_index, col_index, QTableWidgetItem(str(value)))



