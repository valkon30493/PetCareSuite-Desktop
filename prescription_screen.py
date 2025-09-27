# prescription_screen.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTableWidget, QTableWidgetItem, QLineEdit, QSpinBox,
    QDateEdit, QPushButton, QMessageBox, QFileDialog, QCompleter
)
from PySide6.QtCore import Qt, QDate
import csv
import prescriptions, sqlite3

class PrescriptionScreen(QWidget):
    def __init__(self, all_patients):
        super().__init__()
        self.setWindowTitle("Prescription Management")
        self.all_patients = all_patients  # list of (id,name)
        self.selected_rx_id = None

        main = QVBoxLayout(self)

        # Table
        self.table = QTableWidget(0,8)
        self.table.setHorizontalHeaderLabels([
            "RX","Patient","Medication","Dose","Freq","Qty","Start","End"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.on_select)
        main.addWidget(self.table)

        # Form
        form = QFormLayout()
        self.pat_in   = QLineEdit()
        self.pat_in.setCompleter(QCompleter([n for _,n in all_patients]))
        self.med_in   = QLineEdit()
        self.dose_in  = QLineEdit()
        self.freq_in  = QLineEdit()
        self.qty_in   = QSpinBox(); self.qty_in.setMinimum(1)
        self.start_in = QDateEdit(QDate.currentDate()); self.start_in.setCalendarPopup(True)
        self.end_in   = QDateEdit(QDate.currentDate());   self.end_in.setCalendarPopup(True)
        form.addRow("Patient:",      self.pat_in)
        form.addRow("Medication:",   self.med_in)
        form.addRow("Dose:",         self.dose_in)
        form.addRow("Frequency:",    self.freq_in)
        form.addRow("Quantity:",     self.qty_in)
        form.addRow("Start Date:",   self.start_in)
        form.addRow("End Date:",     self.end_in)
        main.addLayout(form)

        # Buttons
        btns = QHBoxLayout()
        for name,slot in [
            ("New",self.on_new),("Save",self.on_save),
            ("Delete",self.on_delete),("Export",self.on_export)
        ]:
            b=QPushButton(name); b.clicked.connect(slot); btns.addWidget(b)
        main.addLayout(btns)

        self.refresh()

    def refresh(self):
        self.table.setRowCount(0)
        for rx in prescriptions.get_prescriptions():
            r=self.table.rowCount(); self.table.insertRow(r)
            for c,v in enumerate(rx):
                if c==1:  # patient_id → name
                    v = next(n for pid,n in self.all_patients if pid==str(v))
                self.table.setItem(r,c, QTableWidgetItem(str(v)))

    def on_select(self):
        r = self.table.currentRow()
        if r<0: return
        vals = [self.table.item(r,c).text() for c in range(8)]
        self.selected_rx_id = int(vals[0])
        self.pat_in  .setText(vals[1])
        self.med_in  .setText(vals[2])
        self.dose_in .setText(vals[3])
        self.freq_in .setText(vals[4])
        self.qty_in  .setValue(int(vals[5]))
        self.start_in.setDate(QDate.fromString(vals[6],"yyyy-MM-dd"))
        self.end_in  .setDate(QDate.fromString(vals[7],"yyyy-MM-dd"))

    def on_new(self):
        self.selected_rx_id = None
        self.pat_in.clear(); self.med_in.clear()
        self.dose_in.clear(); self.freq_in.clear()
        self.qty_in.setValue(1)
        self.start_in.setDate(QDate.currentDate())
        self.end_in  .setDate(QDate.currentDate())

    def on_save(self):
        pat = self.pat_in.text().strip()
        med = self.med_in.text().strip()
        if not pat or not med:
            QMessageBox.warning(self, "Input Error", "Patient & Medication required.")
            return
        pid = next(int(pid) for pid,n in self.all_patients if n==pat)
        dose,freq,qty = self.dose_in.text(), self.freq_in.text(), self.qty_in.value()
        sd = self.start_in.date().toString("yyyy-MM-dd")
        ed = self.end_in.date().toString("yyyy-MM-dd")
        if self.end_in.date() < self.start_in.date():
            QMessageBox.warning(self,"Input Error","End ≥ Start.")
            return

        if self.selected_rx_id:
            prescriptions.update_rx(self.selected_rx_id,
                patient_id=pid, medication=med, dose=dose, frequency=freq,
                quantity=qty, start_date=sd, end_date=ed
            )
        else:
            prescriptions.create_rx(pid,med,dose,freq,qty,sd,ed)
        self.refresh()

    def on_delete(self):
        if not self.selected_rx_id: return
        if QMessageBox.question(self,"Confirm","Delete this RX?")!=QMessageBox.Yes:
            return
        prescriptions.delete_rx(self.selected_rx_id)
        self.on_new(); self.refresh()

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(self,"Save CSV","prescriptions.csv","*.csv")
        if not path: return
        rows = prescriptions.get_prescriptions()
        with open(path,"w",newline="") as f:
            w=csv.writer(f)
            w.writerow(["RX","Patient","Medication","Dose","Freq","Qty","Start","End"])
            for rx in rows:
                # replace patient_id with name
                pid = next(n for pid,n in self.all_patients if pid==str(rx[1]))
                w.writerow([rx[0],pid,*rx[2:]])
        QMessageBox.information(self,"Exported",f"Saved to {path}")

