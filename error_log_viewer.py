# error_log_viewer.py
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QPushButton,
    QDateEdit, QHeaderView, QHBoxLayout, QMessageBox, QFileDialog
)
from db import connect as _connect
from PySide6.QtCore import QDate
import csv
from backup import LOG_PATH


class ErrorLogViewer(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Error Log Viewer")
        self.setGeometry(200, 200, 800, 400)

        layout = QVBoxLayout()

        # Date filters
        filter_layout = QHBoxLayout()
        self.start_date_filter = QDateEdit()
        self.start_date_filter.setCalendarPopup(True)
        # default to last 7 days for convenience
        self.start_date_filter.setDate(QDate.currentDate().addDays(-7))

        self.end_date_filter = QDateEdit()
        self.end_date_filter.setCalendarPopup(True)
        self.end_date_filter.setDate(QDate.currentDate())

        filter_layout.addWidget(self.start_date_filter)
        filter_layout.addWidget(self.end_date_filter)

        self.search_button = QPushButton("Filter Logs")
        self.search_button.clicked.connect(self.load_logs)
        filter_layout.addWidget(self.search_button)

        layout.addLayout(filter_layout)

        # Error Log Table â€â€ 2 columns to match DB schema
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(3)
        self.log_table.setHorizontalHeaderLabels(["Timestamp", "Error Type", "Error Message"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.log_table)

        # Export
        self.export_button = QPushButton("Export to CSV")
        self.export_button.clicked.connect(self.export_logs_to_csv)
        layout.addWidget(self.export_button)

        self.setLayout(layout)

        # Initial load
        self.load_logs()

    def load_logs(self):
        """Load logs from the database with date filtering (inclusive)."""
        self.log_table.setRowCount(0)

        start_date = self.start_date_filter.date().toString("yyyy-MM-dd")
        end_date   = self.end_date_filter.date().toString("yyyy-MM-dd")

        try:
            conn = _connect()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT timestamp, error_type, error_message
                  FROM error_logs
                 WHERE DATE(timestamp) BETWEEN DATE(?) AND DATE(?)
                 ORDER BY timestamp DESC
            """, (start_date, end_date))
            logs = cursor.fetchall()
            conn.close()

            for row_index, (ts, type, msg) in enumerate(logs):
                self.log_table.insertRow(row_index)
                self.log_table.setItem(row_index, 0, QTableWidgetItem(str(ts)))
                self.log_table.setItem(row_index, 1, QTableWidgetItem(str(type)))
                self.log_table.setItem(row_index, 2, QTableWidgetItem(str(msg)))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load logs: {str(e)}")

    def export_logs_to_csv(self):
        """Export logs to a CSV file (2 columns)."""
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Logs", "error_logs.csv", "CSV Files (*.csv)")
        if not file_path:
            return

        try:
            conn = _connect()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, error_type, error_message
                  FROM error_logs
                 ORDER BY timestamp DESC
            """)
            logs = cursor.fetchall()
            conn.close()

            with open(file_path, mode='w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(["Timestamp", "Error Type", "Error Message"])
                w.writerows(logs)

            QMessageBox.information(self, "Export Successful", f"Logs saved to {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"An error occurred while exporting: {str(e)}")



