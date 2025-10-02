import csv
import sqlite3
from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from db import connect as _connect


class PatientManagementScreen(QWidget):
    # Signal to notify patient list updates
    patient_list_updated = Signal()
    # Signal to navigate to appointment scheduling (patient_id, patient_name)
    patient_selected = Signal(int, str)
    create_medical_record = Signal(int, str)
    create_consent_requested = Signal(int, str)  # patient_id, patient_name

    def __init__(self):
        super().__init__()

        # â â â  Layouts â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        main_layout = QVBoxLayout()
        search_layout = QHBoxLayout()
        form_layout = QFormLayout()
        btn_layout = QHBoxLayout()

        # â â â  Search & Filters â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name, breed, or owner…")
        self.search_input.returnPressed.connect(self.search_patients)
        search_layout.addWidget(self.search_input)

        self.species_filter = QComboBox()
        self.species_filter.addItems(["All Species", "Dog", "Cat", "Bird", "Reptile"])
        self.species_filter.currentIndexChanged.connect(self.search_patients)
        search_layout.addWidget(self.species_filter)

        self.min_age_filter = QSpinBox()
        self.min_age_filter.setRange(0, 100)
        self.min_age_filter.setPrefix("Min Age: ")
        self.min_age_filter.valueChanged.connect(self.search_patients)
        search_layout.addWidget(self.min_age_filter)

        self.max_age_filter = QSpinBox()
        self.max_age_filter.setRange(0, 100)
        self.max_age_filter.setPrefix("Max Age: ")
        self.max_age_filter.valueChanged.connect(self.search_patients)
        search_layout.addWidget(self.max_age_filter)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.search_patients)
        search_layout.addWidget(search_btn)

        # â â â  Patient Detail Form â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        self.name_input = QLineEdit()
        self.species_input = QComboBox()
        self.species_input.addItems(["Dog", "Cat", "Bird", "Reptile", "Other"])
        self.breed_input = QLineEdit()

        age_layout = QHBoxLayout()
        self.age_years_input = QSpinBox()
        self.age_years_input.setRange(0, 100)
        self.age_years_input.setPrefix("Years: ")
        age_layout.addWidget(self.age_years_input)

        self.age_months_input = QSpinBox()
        self.age_months_input.setRange(0, 11)
        self.age_months_input.setPrefix("Months: ")
        age_layout.addWidget(self.age_months_input)

        self.owner_name_input = QLineEdit()
        self.owner_contact_input = QLineEdit()
        self.owner_email_input = QLineEdit()

        form_layout.addRow("Patient Name:", self.name_input)
        form_layout.addRow("Species:", self.species_input)
        form_layout.addRow("Breed:", self.breed_input)
        form_layout.addRow("Age:", age_layout)
        form_layout.addRow("Owner Name:", self.owner_name_input)
        form_layout.addRow("Owner Contact:", self.owner_contact_input)
        form_layout.addRow("Owner Email:", self.owner_email_input)

        # â â â  Action Buttons â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        self.add_button = QPushButton("Add Patient")
        self.edit_button = QPushButton("Edit Patient")
        self.delete_button = QPushButton("Delete Patient")
        self.view_button = QPushButton("View Details")
        self.schedule_button = QPushButton("Schedule Appointment")
        self.create_medrec_button = QPushButton("Create Medical Record")
        self.create_consent_button = QPushButton("Create Consent")
        view_all_btn = QPushButton("View All")
        export_btn = QPushButton("Export to CSV")

        for btn in (
            self.edit_button,
            self.delete_button,
            self.view_button,
            self.schedule_button,
            self.create_medrec_button,
            self.create_consent_button,
        ):
            btn.setEnabled(False)

        self.add_button.clicked.connect(self.add_patient)
        self.edit_button.clicked.connect(self.update_patient)
        self.delete_button.clicked.connect(self.delete_patient)
        self.view_button.clicked.connect(self.view_details)
        self.schedule_button.clicked.connect(self.navigate_to_appointment_scheduling)
        self.create_medrec_button.clicked.connect(self.open_medical_record)
        self.create_consent_button.clicked.connect(self._create_consent_from_selected)
        view_all_btn.clicked.connect(self.load_patients)
        export_btn.clicked.connect(self.export_to_csv)

        for btn in (
            self.add_button,
            self.edit_button,
            self.delete_button,
            self.view_button,
            view_all_btn,
            export_btn,
            self.schedule_button,
            self.create_medrec_button,
            self.create_consent_button,
        ):
            btn_layout.addWidget(btn)

        # â â â  Patient Table â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        self.patient_table = QTableWidget()
        self.patient_table.setColumnCount(8)
        self.patient_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Name",
                "Species",
                "Breed",
                "Age",
                "Owner Name",
                "Owner Contact",
                "Owner Email",
            ]
        )
        self.patient_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.patient_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.patient_table.itemSelectionChanged.connect(self.load_selected_patient)

        # â â â  Assemble Layout â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        main_layout.addLayout(search_layout)
        main_layout.addLayout(form_layout)
        main_layout.addLayout(btn_layout)
        main_layout.addWidget(self.patient_table)
        self.setLayout(main_layout)

        # â â â  State â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        self.selected_patient_id = None

        # â â â  Signals â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        self.patient_list_updated.connect(self.load_patients)

        # â â â  Initial Data Load â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â â
        self.load_patients()

    def add_patient(self):
        name = self.name_input.text().strip()
        species = self.species_input.currentText()
        breed = self.breed_input.text().strip()
        years = self.age_years_input.value()
        months = self.age_months_input.value()
        oname = self.owner_name_input.text().strip()
        ocontact = self.owner_contact_input.text().strip()
        oemail = self.owner_email_input.text().strip()

        if not (name and oname):
            QMessageBox.warning(
                self, "Input Error", "Patient name and owner name are required."
            )
            return

        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO patients
              (name, species, breed, age_years, age_months, owner_name, owner_contact, owner_email)
            VALUES (?,?,?,?,?,?,?,?)
        """,
            (name, species, breed, years, months, oname, ocontact, oemail),
        )
        conn.commit()
        conn.close()

        self.clear_inputs()
        self.patient_list_updated.emit()
        QMessageBox.information(self, "Success", "Patient added successfully.")

    def update_patient(self):
        if not self.selected_patient_id:
            QMessageBox.warning(self, "No Patient Selected", "Select a patient first.")
            return

        name = self.name_input.text().strip()
        species = self.species_input.currentText()
        breed = self.breed_input.text().strip()
        years = self.age_years_input.value()
        months = self.age_months_input.value()
        oname = self.owner_name_input.text().strip()
        ocontact = self.owner_contact_input.text().strip()
        oemail = self.owner_email_input.text().strip()

        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE patients
               SET name=?, species=?, breed=?,
                   age_years=?, age_months=?,
                   owner_name=?, owner_contact=?, owner_email=?
             WHERE patient_id=?
        """,
            (
                name,
                species,
                breed,
                years,
                months,
                oname,
                ocontact,
                oemail,
                self.selected_patient_id,
            ),
        )
        conn.commit()
        conn.close()

        self.clear_inputs()
        self.patient_list_updated.emit()

    def delete_patient(self):
        if not self.selected_patient_id:
            QMessageBox.warning(self, "No Patient Selected", "Select a patient first.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete this patient?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            conn = _connect()
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM patients WHERE patient_id=?", (self.selected_patient_id,)
            )
            conn.commit()
            conn.close()
            self.clear_inputs()
            self.patient_list_updated.emit()

    def view_details(self):
        if not self.selected_patient_id:
            QMessageBox.warning(self, "No Patient Selected", "Select a patient first.")
            return

        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT name, species, breed, age_years, age_months,
                   owner_name, owner_contact, owner_email
              FROM patients
             WHERE patient_id=?
        """,
            (self.selected_patient_id,),
        )
        p = cur.fetchone()
        conn.close()

        if not p:
            QMessageBox.warning(self, "Error", "Could not load details.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Patient Details")
        dlg_layout = QVBoxLayout()
        labels = [
            f"Name: {p[0]}",
            f"Species: {p[1]}",
            f"Breed: {p[2]}",
            f"Age: {p[3]}y {p[4]}m",
            f"Owner: {p[5]}",
            f"Contact: {p[6]}",
            f"Email: {p[7]}",
        ]
        for txt in labels:
            dlg_layout.addWidget(QLabel(txt))

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dialog.accept)
        dlg_layout.addWidget(btns)

        dialog.setLayout(dlg_layout)
        dialog.exec()

    def export_to_csv(self):
        default_fn = f"patients_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", default_fn, "CSV Files (*.csv)"
        )
        if not path:
            return

        rows = []
        for r in range(self.patient_table.rowCount()):
            rows.append(
                [
                    self.patient_table.item(r, c).text()
                    for c in range(self.patient_table.columnCount())
                ]
            )

        if not rows:
            QMessageBox.warning(self, "No Data", "Nothing to export.")
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        self.patient_table.horizontalHeaderItem(c).text()
                        for c in range(self.patient_table.columnCount())
                    ]
                )
                writer.writerows(rows)
            QMessageBox.information(self, "Exported", f"Saved to {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def search_patients(self):
        term = self.search_input.text().strip()
        species = self.species_filter.currentText()
        min_age = self.min_age_filter.value()
        max_age = self.max_age_filter.value()

        query = """
            SELECT patient_id, name, species, breed,
                   age_years || 'y ' || age_months || 'm' AS age,
                   owner_name, owner_contact, owner_email
              FROM patients
             WHERE 1=1
        """
        params = []

        if term:
            query += " AND (name LIKE ? OR breed LIKE ? OR owner_name LIKE ?)"
            pat = f"%{term}%"
            params += [pat, pat, pat]

        if species != "All Species":
            query += " AND lower(species)=?"
            params.append(species.lower())

        if min_age > 0:
            query += " AND age_years >= ?"
            params.append(min_age)
        if max_age > 0:
            query += " AND age_years <= ?"
            params.append(max_age)

        conn = _connect()
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()

        self._populate_table(rows)

    def load_patients(self):
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT patient_id, name, species, breed,
                   age_years || 'y ' || age_months || 'm' AS age,
                   owner_name, owner_contact, owner_email
              FROM patients
        """
        )
        rows = cur.fetchall()
        conn.close()

        self._populate_table(rows)

    def _populate_table(self, rows):
        self.patient_table.setRowCount(0)
        for r, row in enumerate(rows):
            self.patient_table.insertRow(r)
            for c, val in enumerate(row):
                self.patient_table.setItem(r, c, QTableWidgetItem(str(val)))
        self.clear_inputs()

    def load_selected_patient(self):
        r = self.patient_table.currentRow()
        if r < 0:
            return

        self.selected_patient_id = int(self.patient_table.item(r, 0).text())
        self.name_input.setText(self.patient_table.item(r, 1).text())
        self.species_input.setCurrentText(self.patient_table.item(r, 2).text())
        self.breed_input.setText(self.patient_table.item(r, 3).text())

        age_text = self.patient_table.item(r, 4).text()
        yrs, rest = age_text.split("y")
        mths = rest.strip().strip("m")
        self.age_years_input.setValue(int(yrs))
        self.age_months_input.setValue(int(mths))

        self.owner_name_input.setText(self.patient_table.item(r, 5).text())
        self.owner_contact_input.setText(self.patient_table.item(r, 6).text())
        self.owner_email_input.setText(self.patient_table.item(r, 7).text())

        # Enable action buttons
        self.edit_button.setEnabled(True)
        self.delete_button.setEnabled(True)
        self.view_button.setEnabled(True)
        self.schedule_button.setEnabled(True)
        self.create_medrec_button.setEnabled(True)
        self.create_consent_button.setEnabled(True)
        self.add_button.setEnabled(False)

    def navigate_to_appointment_scheduling(self):
        if not self.selected_patient_id:
            QMessageBox.warning(
                self, "No Patient Selected", "Please select a patient first."
            )
            return

        name = self.name_input.text().strip()
        self.patient_selected.emit(self.selected_patient_id, name)
        self.clear_inputs()

    def open_medical_record(self):
        if not self.selected_patient_id:
            QMessageBox.warning(
                self, "No Patient Selected", "Please select a patient first."
            )
            return
        name = self.name_input.text().strip()
        self.create_medical_record.emit(self.selected_patient_id, name)

    def _create_consent_from_selected(self):
        if not self.selected_patient_id:
            QMessageBox.warning(
                self, "No Patient Selected", "Please select a patient first."
            )
            return
        name = self.name_input.text().strip()
        self.create_consent_requested.emit(self.selected_patient_id, name)

    def clear_inputs(self):
        self.name_input.clear()
        self.species_input.setCurrentIndex(0)
        self.breed_input.clear()
        self.age_years_input.setValue(0)
        self.age_months_input.setValue(0)
        self.owner_name_input.clear()
        self.owner_contact_input.clear()
        self.owner_email_input.clear()

        self.selected_patient_id = None
        self.edit_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        self.view_button.setEnabled(False)
        self.schedule_button.setEnabled(False)
        self.create_medrec_button.setEnabled(False)
        self.create_consent_button.setEnabled(False)
        self.add_button.setEnabled(True)
