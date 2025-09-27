import sqlite3
import csv
from datetime import datetime
from io import BytesIO
from PIL import Image
from db import connect as _connect

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QPushButton, QFileDialog, QMessageBox, QHBoxLayout, QDateEdit
)
from PySide6.QtCore import QDate
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.pagesizes import A4

class ReportsAnalyticsScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Reports & Analytics")
        layout = QVBoxLayout(self)

        self.start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.start_date.setCalendarPopup(True)
        self.end_date = QDateEdit(QDate.currentDate())
        self.end_date.setCalendarPopup(True)

        tabs = QTabWidget()
        tabs.addTab(self.revenue_by_month_tab(), "Revenue by Month")
        tabs.addTab(self.unpaid_invoices_tab(), "Unpaid Invoices")
        tabs.addTab(self.appointments_by_species_tab(), "Appointments by Species")
        tabs.addTab(self.top_items_tab(), "Top Medications/Items")
        tabs.addTab(self.busiest_days_tab(), "Busiest Days/Times")
        tabs.addTab(self.appointments_by_vet_tab(), "Appointments by Vet")

        layout.addWidget(tabs)


    def revenue_by_month_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.revenue_start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.revenue_end_date = QDateEdit(QDate.currentDate())
        self.revenue_start_date.setCalendarPopup(True)
        self.revenue_end_date.setCalendarPopup(True)
        self.revenue_start_date.setDisplayFormat("yyyy-MM-dd")
        self.revenue_end_date.setDisplayFormat("yyyy-MM-dd")

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:"))
        filter_row.addWidget(self.revenue_start_date)
        filter_row.addWidget(QLabel("To:"))
        filter_row.addWidget(self.revenue_end_date)

        filter_btn = QPushButton("Apply Date Filter")
        filter_btn.clicked.connect(lambda: self.load_revenue_chart(layout))
        filter_row.addWidget(filter_btn)

        layout.addLayout(filter_row)

        self.revenue_canvas_holder = QVBoxLayout()
        layout.addLayout(self.revenue_canvas_holder)

        export_btn = QPushButton("Export to PDF")
        export_btn.clicked.connect(self.export_revenue_pdf)
        layout.addWidget(export_btn)

        self.load_revenue_chart(layout)
        return widget

    def load_revenue_chart(self, layout):
        for i in reversed(range(self.revenue_canvas_holder.count())):
            widget_to_remove = self.revenue_canvas_holder.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)

        fig = Figure(figsize=(6, 4))
        canvas = FigureCanvas(fig)
        ax = fig.add_subplot(111)

        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT strftime('%Y-%m', created_at) AS month, SUM(final_amount)
            FROM invoices
            WHERE DATE(created_at) BETWEEN DATE(?) AND DATE(?)
            GROUP BY month
            ORDER BY month
        """, (
            self.revenue_start_date.date().toString("yyyy-MM-dd"),
            self.revenue_end_date.date().toString("yyyy-MM-dd")
        ))
        data = cursor.fetchall()
        conn.close()

        if data:
            months, totals = zip(*data)
            ax.bar(months, totals)
            ax.set_title("Revenue by Month")
            ax.set_ylabel("€")
            ax.set_xlabel("Month")
            ax.tick_params(axis='x', rotation=45)
        else:
            ax.text(0.5, 0.5, "No data", ha='center')

        self.revenue_canvas_holder.addWidget(canvas)
        self.revenue_figure = fig
        self.revenue_data = data

    def export_revenue_pdf(self):
        if not getattr(self, 'revenue_data', None):
            QMessageBox.warning(self, "No Data", "No revenue data available to export.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "revenue_report.pdf", "PDF Files (*.pdf)")
        if not path:
            return

        # Create a fresh figure for export
        export_fig = Figure(figsize=(6, 3.5))
        ax = export_fig.add_subplot(111)

        months, totals = zip(*self.revenue_data)
        ax.bar(months, totals)
        ax.set_title("Revenue by Month")
        ax.set_ylabel("€")
        ax.set_xlabel("Month")
        ax.tick_params(axis='x', rotation=45)
        export_fig.tight_layout()

        buf = BytesIO()
        export_fig.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        chart_image = Image.open(buf)

        pdf = pdf_canvas.Canvas(path, pagesize=A4)
        width, height = A4
        pdf.setTitle("Revenue Report")

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, height - 50, "Pet Wellness Vets – Revenue Summary")

        pdf.setFont("Helvetica", 10)
        date_range = f"From {self.revenue_start_date.date().toString('yyyy-MM-dd')} to {self.revenue_end_date.date().toString('yyyy-MM-dd')}"
        pdf.drawString(50, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        pdf.drawString(50, height - 85, date_range)

        pdf.drawInlineImage(chart_image, 50, height - 400, width=500, height=250)

        y = height - 420
        total_revenue = 0
        pdf.setFont("Helvetica", 10)
        for month, amount in self.revenue_data:
            pdf.drawString(60, y, f"{month}: €{amount:.2f}")
            total_revenue += amount
            y -= 15

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(60, y - 10, f"Total Revenue: €{total_revenue:.2f}")
        pdf.save()

        QMessageBox.information(self, "Exported", f"Report saved to {path}")

    def unpaid_invoices_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.unpaid_table = QTableWidget()
        self.unpaid_table.setColumnCount(5)
        self.unpaid_table.setHorizontalHeaderLabels(["Invoice ID", "Appointment ID", "Patient", "Amount Due", "Created At"])
        self.unpaid_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.invoice_id, i.appointment_id, p.name,
                   (i.final_amount - IFNULL((SELECT SUM(amount_paid) FROM payment_history WHERE invoice_id = i.invoice_id), 0)) AS due,
                   i.created_at
            FROM invoices i
            JOIN appointments a ON i.appointment_id = a.appointment_id
            JOIN patients p ON a.patient_id = p.patient_id
            WHERE i.payment_status != 'Paid'
        """)
        rows = cursor.fetchall()
        conn.close()

        self.unpaid_table.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            for c_idx, val in enumerate(row):
                item = QTableWidgetItem(f"{val:.2f}" if isinstance(val, float) else str(val))
                self.unpaid_table.setItem(r_idx, c_idx, item)

        layout.addWidget(QLabel("Unpaid or Partially Paid Invoices"))
        layout.addWidget(self.unpaid_table)

        export_csv_btn = QPushButton("Export to CSV")
        export_csv_btn.clicked.connect(self.export_unpaid_csv)
        layout.addWidget(export_csv_btn)

        return widget

    def export_unpaid_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "unpaid_invoices.csv", "CSV Files (*.csv)")
        if not path:
            return

        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Invoice ID", "Appointment ID", "Patient", "Amount Due", "Created At"])
            for r in range(self.unpaid_table.rowCount()):
                row = [self.unpaid_table.item(r, c).text() for c in range(self.unpaid_table.columnCount())]
                writer.writerow(row)

        QMessageBox.information(self, "Export Complete", f"Saved to {path}")

    def appointments_by_species_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.species_start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.species_end_date = QDateEdit(QDate.currentDate())
        self.species_start_date.setCalendarPopup(True)
        self.species_end_date.setCalendarPopup(True)
        self.species_start_date.setDisplayFormat("yyyy-MM-dd")
        self.species_end_date.setDisplayFormat("yyyy-MM-dd")

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:"))
        filter_row.addWidget(self.species_start_date)
        filter_row.addWidget(QLabel("To:"))
        filter_row.addWidget(self.species_end_date)

        filter_btn = QPushButton("Apply Date Filter")
        filter_btn.clicked.connect(lambda: self.load_species_chart(layout))
        filter_row.addWidget(filter_btn)

        layout.addLayout(filter_row)

        self.species_canvas_holder = QVBoxLayout()
        layout.addLayout(self.species_canvas_holder)

        export_btn = QPushButton("Export to PDF")
        export_btn.clicked.connect(self.export_species_pdf)
        layout.addWidget(export_btn)

        self.load_species_chart(layout)
        return widget

    def load_species_chart(self, layout):
        for i in reversed(range(self.species_canvas_holder.count())):
            widget_to_remove = self.species_canvas_holder.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)

        fig = Figure(figsize=(6, 4))
        canvas = FigureCanvas(fig)
        ax = fig.add_subplot(111)

        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.species, COUNT(*)
            FROM appointments a
            JOIN patients p ON a.patient_id = p.patient_id
            WHERE DATE(a.date_time) BETWEEN DATE(?) AND DATE(?)
            GROUP BY p.species
        """, (
            self.species_start_date.date().toString("yyyy-MM-dd"),
            self.species_end_date.date().toString("yyyy-MM-dd")
        ))
        data = cursor.fetchall()
        conn.close()

        if data:
            species, counts = zip(*data)
            ax.pie(counts, labels=species, autopct='%1.1f%%', startangle=140)
            ax.set_title("Appointments by Species")
        else:
            ax.text(0.5, 0.5, "No data", ha='center')

        self.species_canvas_holder.addWidget(canvas)
        self.species_figure = fig
        self.species_data = data

    def export_species_pdf(self):
        if not getattr(self, 'species_data', None):
            QMessageBox.warning(self, "No Data", "No species data to export.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "species_report.pdf", "PDF Files (*.pdf)")
        if not path:
            return

        # Re-render chart to avoid resizing the in-app figure
        export_fig = Figure(figsize=(6, 3.5))
        ax = export_fig.add_subplot(111)

        species, counts = zip(*self.species_data)
        ax.pie(counts, labels=species, autopct='%1.1f%%', startangle=140)
        ax.set_title("Appointments by Species")
        export_fig.tight_layout()

        buf = BytesIO()
        export_fig.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        chart_image = Image.open(buf)

        pdf = pdf_canvas.Canvas(path, pagesize=A4)
        width, height = A4
        pdf.setTitle("Species Report")

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, height - 50, "Pet Wellness Vets – Appointments by Species")

        pdf.setFont("Helvetica", 10)
        date_range = f"From {self.species_start_date.date().toString('yyyy-MM-dd')} to {self.species_end_date.date().toString('yyyy-MM-dd')}"
        pdf.drawString(50, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        pdf.drawString(50, height - 85, date_range)

        pdf.drawInlineImage(chart_image, 50, height - 400, width=500, height=250)

        y = height - 420
        pdf.setFont("Helvetica", 10)
        for specie, count in self.species_data:
            pdf.drawString(60, y, f"{specie}: {count} appointments")
            y -= 15

        pdf.save()
        QMessageBox.information(self, "Exported", f"Report saved to {path}")

    def top_items_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.items_start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.items_end_date = QDateEdit(QDate.currentDate())
        self.items_start_date.setCalendarPopup(True)
        self.items_end_date.setCalendarPopup(True)
        self.items_start_date.setDisplayFormat("yyyy-MM-dd")
        self.items_end_date.setDisplayFormat("yyyy-MM-dd")

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:"))
        filter_row.addWidget(self.items_start_date)
        filter_row.addWidget(QLabel("To:"))
        filter_row.addWidget(self.items_end_date)

        filter_btn = QPushButton("Apply Date Filter")
        filter_btn.clicked.connect(lambda: self.load_top_items_chart(layout))
        filter_row.addWidget(filter_btn)

        layout.addLayout(filter_row)

        self.top_items_canvas_holder = QVBoxLayout()
        layout.addLayout(self.top_items_canvas_holder)

        export_btn = QPushButton("Export to PDF")
        export_btn.clicked.connect(self.export_top_items_pdf)
        layout.addWidget(export_btn)

        self.load_top_items_chart(layout)
        return widget

    def load_top_items_chart(self, layout):
        for i in reversed(range(self.top_items_canvas_holder.count())):
            widget_to_remove = self.top_items_canvas_holder.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)

        fig = Figure(figsize=(6, 4))
        canvas = FigureCanvas(fig)
        ax = fig.add_subplot(111)

        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ii.description, SUM(ii.quantity) as total_sold
            FROM invoice_items ii
            JOIN invoices i ON i.invoice_id = ii.invoice_id
            WHERE DATE(i.created_at) BETWEEN DATE(?) AND DATE(?)
            GROUP BY ii.description
            ORDER BY total_sold DESC
            LIMIT 10
        """, (
            self.items_start_date.date().toString("yyyy-MM-dd"),
            self.items_end_date.date().toString("yyyy-MM-dd")
        ))
        data = cursor.fetchall()
        conn.close()

        if data:
            items, counts = zip(*data)
            ax.barh(items, counts)
            ax.set_title("Top-Selling Medications/Items")
            ax.set_xlabel("Units Sold")
            ax.invert_yaxis()
        else:
            ax.text(0.5, 0.5, "No data", ha='center')

        self.top_items_canvas_holder.addWidget(canvas)
        self.top_items_figure = fig
        self.top_items_data = data

    def export_top_items_pdf(self):
        if not getattr(self, 'top_items_data', None):
            QMessageBox.warning(self, "No Data", "No top items data to export.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "top_items_report.pdf", "PDF Files (*.pdf)")
        if not path:
            return

        # Re-render chart into separate export figure
        export_fig = Figure(figsize=(6, 3.5))
        ax = export_fig.add_subplot(111)

        items, counts = zip(*self.top_items_data)
        ax.barh(items, counts)
        ax.set_title("Top-Selling Medications/Items")
        ax.set_xlabel("Units Sold")
        ax.invert_yaxis()
        export_fig.tight_layout()

        buf = BytesIO()
        export_fig.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        chart_image = Image.open(buf)

        pdf = pdf_canvas.Canvas(path, pagesize=A4)
        width, height = A4
        pdf.setTitle("Top Items Report")

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, height - 50, "Pet Wellness Vets – Top Medications/Items")

        pdf.setFont("Helvetica", 10)
        date_range = f"From {self.items_start_date.date().toString('yyyy-MM-dd')} to {self.items_end_date.date().toString('yyyy-MM-dd')}"
        pdf.drawString(50, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        pdf.drawString(50, height - 85, date_range)

        pdf.drawInlineImage(chart_image, 50, height - 400, width=500, height=250)

        y = height - 420
        pdf.setFont("Helvetica", 10)
        for item, qty in self.top_items_data:
            pdf.drawString(60, y, f"{item}: {qty} units")
            y -= 15

        pdf.save()
        QMessageBox.information(self, "Exported", f"Report saved to {path}")

    def busiest_days_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.busiest_start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.busiest_end_date = QDateEdit(QDate.currentDate())
        self.busiest_start_date.setCalendarPopup(True)
        self.busiest_end_date.setCalendarPopup(True)
        self.busiest_start_date.setDisplayFormat("yyyy-MM-dd")
        self.busiest_end_date.setDisplayFormat("yyyy-MM-dd")

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:"))
        filter_row.addWidget(self.busiest_start_date)
        filter_row.addWidget(QLabel("To:"))
        filter_row.addWidget(self.busiest_end_date)

        filter_btn = QPushButton("Apply Date Filter")
        filter_btn.clicked.connect(lambda: self.load_busiest_days_chart(layout))
        filter_row.addWidget(filter_btn)

        layout.addLayout(filter_row)

        self.busiest_canvas_holder = QVBoxLayout()
        layout.addLayout(self.busiest_canvas_holder)

        export_btn = QPushButton("Export to PDF")
        export_btn.clicked.connect(self.export_busiest_days_pdf)
        layout.addWidget(export_btn)

        self.load_busiest_days_chart(layout)
        return widget

    def load_busiest_days_chart(self, layout):
        for i in reversed(range(self.busiest_canvas_holder.count())):
            widget_to_remove = self.busiest_canvas_holder.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)

        fig = Figure(figsize=(6, 4))
        canvas = FigureCanvas(fig)
        ax = fig.add_subplot(111)

        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT strftime('%w', date_time) AS weekday, COUNT(*)
            FROM appointments
            WHERE DATE(date_time) BETWEEN DATE(?) AND DATE(?)
            GROUP BY weekday
        """, (
            self.busiest_start_date.date().toString("yyyy-MM-dd"),
            self.busiest_end_date.date().toString("yyyy-MM-dd")
        ))
        data = cursor.fetchall()
        conn.close()

        days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        counts = [0] * 7
        for weekday, count in data:
            counts[int(weekday)] = count

        ax.bar(days, counts)
        ax.set_title("Appointments by Day of Week")
        ax.set_ylabel("Number of Appointments")
        ax.set_xticks(range(len(days)))
        ax.set_xticklabels(days, rotation=45)


        self.busiest_canvas_holder.addWidget(canvas)
        self.busiest_figure = fig
        self.busiest_data = counts

    def export_busiest_days_pdf(self):
        if not getattr(self, 'busiest_data', None):
            QMessageBox.warning(self, "No Data", "No busiest day data to export.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "busiest_days.pdf", "PDF Files (*.pdf)")
        if not path:
            return

        # Re-render chart into new figure for PDF
        export_fig = Figure(figsize=(6, 3.5))
        ax = export_fig.add_subplot(111)

        days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        ax.bar(range(7), self.busiest_data)
        ax.set_title("Appointments by Day of Week")
        ax.set_ylabel("Number of Appointments")
        ax.set_xticks(range(7))
        ax.set_xticklabels(days, rotation=45)
        export_fig.tight_layout()

        buf = BytesIO()
        export_fig.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        chart_image = Image.open(buf)

        pdf = pdf_canvas.Canvas(path, pagesize=A4)
        width, height = A4
        pdf.setTitle("Busiest Days Report")

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, height - 50, "Pet Wellness Vets – Busiest Days")

        pdf.setFont("Helvetica", 10)
        date_range = f"From {self.busiest_start_date.date().toString('yyyy-MM-dd')} to {self.busiest_end_date.date().toString('yyyy-MM-dd')}"
        pdf.drawString(50, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        pdf.drawString(50, height - 85, date_range)

        pdf.drawInlineImage(chart_image, 50, height - 400, width=500, height=250)

        y = height - 420
        pdf.setFont("Helvetica", 10)
        for i, count in enumerate(self.busiest_data):
            pdf.drawString(60, y, f"{days[i]}: {count} appointments")
            y -= 15

        pdf.save()
        QMessageBox.information(self, "Exported", f"Report saved to {path}")

    def appointments_by_vet_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.vet_start_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.vet_end_date = QDateEdit(QDate.currentDate())
        self.vet_start_date.setCalendarPopup(True)
        self.vet_end_date.setCalendarPopup(True)
        self.vet_start_date.setDisplayFormat("yyyy-MM-dd")
        self.vet_end_date.setDisplayFormat("yyyy-MM-dd")

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("From:"))
        filter_row.addWidget(self.vet_start_date)
        filter_row.addWidget(QLabel("To:"))
        filter_row.addWidget(self.vet_end_date)

        filter_btn = QPushButton("Apply Date Filter")
        filter_btn.clicked.connect(lambda: self.load_vet_chart(layout))
        filter_row.addWidget(filter_btn)

        layout.addLayout(filter_row)

        self.vet_canvas_holder = QVBoxLayout()
        layout.addLayout(self.vet_canvas_holder)

        export_btn = QPushButton("Export to PDF")
        export_btn.clicked.connect(self.export_vet_pdf)
        layout.addWidget(export_btn)

        self.load_vet_chart(layout)
        return widget

    def load_vet_chart(self, layout):
        for i in reversed(range(self.vet_canvas_holder.count())):
            widget_to_remove = self.vet_canvas_holder.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)

        fig = Figure(figsize=(6, 4))
        canvas = FigureCanvas(fig)
        ax = fig.add_subplot(111)

        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.veterinarian, COUNT(*)
            FROM appointments a
            WHERE a.veterinarian IS NOT NULL AND a.veterinarian != ''
              AND DATE(a.date_time) BETWEEN DATE(?) AND DATE(?)
            GROUP BY a.veterinarian
        """, (
            self.vet_start_date.date().toString("yyyy-MM-dd"),
            self.vet_end_date.date().toString("yyyy-MM-dd")
        ))
        data = cursor.fetchall()
        conn.close()

        if data:
            vets, counts = zip(*data)
            ax.bar(range(len(vets)), counts)
            ax.set_title("Appointments by Veterinarian")
            ax.set_ylabel("Appointments")
            ax.set_xticks(range(len(vets)))
            ax.set_xticklabels(vets, rotation=45)
        else:
            ax.text(0.5, 0.5, "No data", ha='center')

        self.vet_canvas_holder.addWidget(canvas)
        self.vet_figure = fig
        self.vet_data = data

    def export_vet_pdf(self):
        if not getattr(self, 'vet_data', None):
            QMessageBox.warning(self, "No Data", "No veterinarian data to export.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "appointments_by_vet.pdf", "PDF Files (*.pdf)")
        if not path:
            return

        # Re-render chart to buffer instead of modifying UI figure
        export_fig = Figure(figsize=(6, 3.5))
        ax = export_fig.add_subplot(111)

        vets, counts = zip(*self.vet_data)
        ax.bar(range(len(vets)), counts)
        ax.set_title("Appointments by Veterinarian")
        ax.set_ylabel("Appointments")
        ax.set_xticks(range(len(vets)))
        ax.set_xticklabels(vets, rotation=45)
        export_fig.tight_layout()

        buf = BytesIO()
        export_fig.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        chart_image = Image.open(buf)

        pdf = pdf_canvas.Canvas(path, pagesize=A4)
        width, height = A4
        pdf.setTitle("Appointments by Vet Report")

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(50, height - 50, "Pet Wellness Vets – Appointments by Vet")

        pdf.setFont("Helvetica", 10)
        date_range = f"From {self.vet_start_date.date().toString('yyyy-MM-dd')} to {self.vet_end_date.date().toString('yyyy-MM-dd')}"
        pdf.drawString(50, height - 70, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        pdf.drawString(50, height - 85, date_range)

        pdf.drawInlineImage(chart_image, 50, height - 400, width=500, height=250)

        y = height - 420
        pdf.setFont("Helvetica", 10)
        for vet, count in self.vet_data:
            pdf.drawString(60, y, f"{vet}: {count} appointments")
            y -= 15

        pdf.save()
        QMessageBox.information(self, "Exported", f"Report saved to {path}")
        QMessageBox.information(self, "Exported", f"Report saved to {path}")



