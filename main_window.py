from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QStackedWidget, QPushButton, QMessageBox, QStatusBar,
    QDialog, QDialogButtonBox
)
from PySide6.QtGui import QPixmap, QAction
from patient_management import PatientManagementScreen
from appointment_scheduling import AppointmentSchedulingScreen
from notifications_reminders import NotificationsRemindersScreen
from daily_appointments_calendar import DailyAppointmentsCalendar
from billing_invoicing import BillingInvoicingScreen
from error_log_viewer import ErrorLogViewer
from logger import log_error
from user_management import UserManagementScreen
from user_password_dialog import ChangeMyPasswordDialog
from reports import ZReportWidget
from reports_analytics import ReportsAnalyticsScreen
from backup import backup_now, resource_path, DB_PATH
from version import APP_VERSION, CHANNEL



# Optional modules with graceful fallbacks
try:
    from inventory_management import InventoryManagementScreen
except Exception as e:
    log_error(f"Inventory import failed: {e}")
    class InventoryManagementScreen(QLabel):
        def __init__(self):
            super().__init__("⚠ï¸ Inventory module failed to load")

try:
    from prescription_management import PrescriptionManagementScreen
except Exception as e:
    log_error(f"Prescription import failed: {e}")
    class PrescriptionManagementScreen(QLabel):
        def __init__(self):
            super().__init__("⚠ï¸ Prescription module failed to load")

# NEW: Medical Records (Visits) import with fallback
try:
    from medical_records import MedicalRecordsScreen
except Exception as e:
    log_error(f"Medical Records import failed: {e}")
    class MedicalRecordsScreen(QLabel):
        def __init__(self):
            super().__init__("ðŸ—'ï¸ Medical Records (Visits) screen not available")

# NEW: Consent Forms import with fallback
try:
    from consent_forms import ConsentFormsScreen
except Exception as e:
    log_error(f"Consent Forms import failed: {e}")
    class ConsentFormsScreen(QLabel):
        def __init__(self):
            super().__init__("📠Consent Forms screen not available")

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About PetCareSuite Desktop")
        self.setModal(True)

        lay = QVBoxLayout(self)

        # Logo
        logo = QLabel()
        pix = QPixmap(resource_path("assets/petcaresuite_icon_256.png"))
        if not pix.isNull():
            logo.setPixmap(pix.scaledToHeight(96, Qt.SmoothTransformation))
            logo.setAlignment(Qt.AlignCenter)
            lay.addWidget(logo)

        # Text
        info = QLabel(
            f"<b>PetCareSuite Desktop</b><br>"
            f"Version {APP_VERSION} ({CHANNEL})<br>"
            "© Valkon Solutions"
        )

        info.setAlignment(Qt.AlignCenter)
        lay.addWidget(info)

        # Environment details (useful for support)
        env = QLabel(f"<small>Database: {DB_PATH}</small>")
        env.setAlignment(Qt.AlignCenter)
        env.setStyleSheet("color:#6b7280;")
        lay.addWidget(env)

        # Close button
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PetCareSuite Desktop")
        self.setGeometry(100, 100, 1600, 900)

        self.user_role = "Guest"
        self.logged_in_username = None

        # Sidebar buttons
        self.patient_button         = QPushButton("Patient Management")
        self.appointment_button     = QPushButton("Appointment Scheduling")
        self.billing_button         = QPushButton("Billing & Invoicing")
        self.inventory_button       = QPushButton("Inventory Management")
        self.prescription_button    = QPushButton("Prescription Management")
        self.medical_records_button = QPushButton("Medical Records")
        self.consent_button         = QPushButton("Consent Forms")
        self.notifications_button   = QPushButton("Notifications & Reminders")
        self.basic_reports_button   = QPushButton("Reports")
        self.analytics_button       = QPushButton("Analytics & Reports")
        self.user_mgmt_button       = QPushButton("User Management")
        self.my_account_button      = QPushButton("My Account")
        self.error_log_button       = QPushButton("View Error Logs")
        self.backup_button          = QPushButton("Backup now")
        self.fullscreen_button      = QPushButton("Exit Full Screen")



        # Screens (instantiate early so we can wire signals)
        self.patient_screen        = PatientManagementScreen()
        self.appointment_screen    = AppointmentSchedulingScreen()
        self.billing_screen        = BillingInvoicingScreen()
        self.inventory_screen      = InventoryManagementScreen()
        self.prescription_screen   = PrescriptionManagementScreen()
        self.medical_records_screen= MedicalRecordsScreen()      # NEW
        self.consent_screen        = ConsentFormsScreen()        # NEW
        self.notifications_screen  = NotificationsRemindersScreen()
        self.reports_screen        = ZReportWidget()
        self.analytics_screen      = ReportsAnalyticsScreen()
        self.user_mgmt_screen      = UserManagementScreen()

        # Stacked widget (NOTE: index order must match button handlers below)
        self.stacked = QStackedWidget()
        for screen in (
            self.patient_screen,          # 0
            self.appointment_screen,      # 1
            self.billing_screen,          # 2
            self.inventory_screen,        # 3
            self.prescription_screen,     # 4
            self.medical_records_screen,  # 5
            self.consent_screen,          # 6
            self.notifications_screen,    # 7
            self.reports_screen,          # 8
            self.analytics_screen,        # 9
            self.user_mgmt_screen         # 10
        ):
            self.stacked.addWidget(screen)

        # Connect buttons to stacked indices
        self.patient_button.clicked.connect(lambda: self.display_screen(0))
        self.appointment_button.clicked.connect(lambda: self.display_screen(1))
        self.billing_button.clicked.connect(lambda: self.display_screen(2))
        self.inventory_button.clicked.connect(lambda: self.display_screen(3))
        self.prescription_button.clicked.connect(lambda: self.display_screen(4))
        self.medical_records_button.clicked.connect(lambda: self.display_screen(5))
        self.consent_button.clicked.connect(lambda: self.display_screen(6))
        self.notifications_button.clicked.connect(lambda: self.display_screen(7))
        self.basic_reports_button.clicked.connect(lambda: self.display_screen(8))
        self.analytics_button.clicked.connect(lambda: self.display_screen(9))
        self.user_mgmt_button.clicked.connect(lambda: self.display_screen(10))
        self.my_account_button.clicked.connect(self.open_account_settings)
        self.error_log_button.clicked.connect(self.open_error_logs)
        self.backup_button.clicked.connect(self.on_backup_now_clicked)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)


        # Sidebar layout
        sidebar_layout = QVBoxLayout()
        for w in (
            self.patient_button, self.appointment_button, self.billing_button,
            self.inventory_button, self.prescription_button,
            self.medical_records_button, self.consent_button,
            self.notifications_button, self.basic_reports_button,
            self.analytics_button, self.user_mgmt_button, self.my_account_button
        ):
            sidebar_layout.addWidget(w)
        sidebar_layout.addStretch(1)
        sidebar_layout.addWidget(self.error_log_button)
        sidebar_layout.addWidget(self.backup_button)
        sidebar_layout.addWidget(self.fullscreen_button)

        # Calendar
        self.calendar_widget = DailyAppointmentsCalendar()

        # Main layout
        main_layout = QHBoxLayout()
        sidebar_plus_cal = QVBoxLayout()
        sidebar_plus_cal.addWidget(self.calendar_widget, 2)
        sidebar_plus_cal.addLayout(sidebar_layout, 3)
        main_layout.addLayout(sidebar_plus_cal, 2)
        main_layout.addWidget(self.stacked, 5)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # --- Help → About menu ---
        help_menu = self.menuBar().addMenu("&Help")
        about_act = QAction("About PetCareSuite…", self)
        about_act.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_act)

        # --- Status bar with subtle branding (add near the end of __init__) ---
        status = QStatusBar()
        brand = QLabel("Powered by Valkon Solutions")
        brand.setStyleSheet("color:#6b7280;")  # soft gray
        status.addPermanentWidget(brand, 1)  # right-aligned
        self.setStatusBar(status)

        # Cross-screen connections (guarded for compatibility)
        try:
            self.patient_screen.patient_list_updated.connect(self.appointment_screen.reload_patients)
        except Exception as e:
            log_error(f"Wire patient_list_updated → reload_patients failed: {e}")

        try:
            self.patient_screen.patient_selected.connect(self.appointment_screen.load_patient_details)
            self.patient_screen.patient_selected.connect(self.handle_patient_selected)
        except Exception as e:
            log_error(f"Wire patient_selected signals failed: {e}")

        # Patient → Medical Records (Visits)
        if hasattr(self.patient_screen, "create_medical_record"):
            try:
                self.patient_screen.create_medical_record.connect(self.open_med_record_from_patient)
            except Exception as e:
                log_error(f"Wire create_medical_record failed: {e}")

        # Appointment → Medical Records (Visits)
        # main_window.py
        self.appointment_screen.open_visit_requested.connect(
            lambda visit_id, _pid: self.open_visit(visit_id)
        )

        # Patient → Consent Forms
        if hasattr(self.patient_screen, "create_consent_requested"):
            try:
                self.patient_screen.create_consent_requested.connect(
                    lambda pid, pname: self._open_consent_for_patient(pid, pname)
                )
            except Exception as e:
                log_error(f"Wire create_consent_requested failed: {e}")

        # Appointment → Notifications pane
        try:
            self.appointment_screen.reminders_list_updated.connect(self.notifications_screen.reload_reminders)
        except Exception as e:
            log_error(f"Wire reminders_list_updated → reload_reminders failed: {e}")

        # Appointment → Billing (single, canonical route)
        try:
            self.appointment_screen.navigate_to_billing_signal.connect(self.navigate_to_billing_screen)
        except Exception as e:
            log_error(f"Wire navigate_to_billing_signal failed: {e}")

        # Billing → Notifications (load reminders by invoice selection)
        try:
            self.billing_screen.invoiceSelected.connect(self.notifications_screen.load_reminders)
        except Exception as e:
            log_error(f"Wire invoiceSelected → notifications.load_reminders failed: {e}")

    # Helpers / plumbing
    def display_screen(self, idx: int):
        self.stacked.setCurrentIndex(idx)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.showNormal()

    def open_error_logs(self):
        ErrorLogViewer().exec()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self.fullscreen_button.setText("Exit Full Screen" if self.isFullScreen() else "Full Screen")

    def handle_patient_selected(self, pid, pname):
        self.appointment_screen.load_patient_details(pid, pname)
        self.display_screen(1)

    # *** Simplified, canonical billing router ***
    def navigate_to_billing_screen(self, appt_id: int):
        try:
            self.billing_screen.open_billing_for_appointment(appt_id)
        except Exception as e:
            log_error(f"open_billing_for_appointment failed: {e}")
            QMessageBox.warning(self, "Billing", "Could not open Billing for this appointment.")
        self.display_screen(2)

    def set_user_context(self, username, role):
        self.logged_in_username = username
        self.user_role = role
        self.adjust_ui_for_role()

    def adjust_ui_for_role(self):
        role = (self.user_role or "").lower()

        if role == "admin":
            self.user_mgmt_button.setEnabled(True)
            return

        if role == "veterinarian":
            self.billing_button.setEnabled(False)
            self.inventory_button.setEnabled(False)
            self.analytics_button.setEnabled(False)
            self.basic_reports_button.setEnabled(False)
            self.user_mgmt_button.setEnabled(False)

        if role == "receptionist":
            self.prescription_button.setEnabled(False)
            self.inventory_button.setEnabled(False)
            self.analytics_button.setEnabled(False)
            self.basic_reports_button.setEnabled(False)
            self.user_mgmt_button.setEnabled(False)

    def open_account_settings(self):
        if not self.logged_in_username:
            QMessageBox.warning(self, "Error", "No logged-in user.")
            return
        dlg = ChangeMyPasswordDialog(self.logged_in_username)
        dlg.exec()

    # NEW: open Medical Records screen focused on a patient (if supported)
    def open_med_record_from_patient(self, patient_id: int, patient_name: str):
        try:
            focus_fn = getattr(self.medical_records_screen, "focus_on_patient", None)
            if callable(focus_fn):
                focus_fn(patient_id, patient_name)
        except Exception as e:
            log_error(f"MedicalRecords focus failed: {e}")
        idx = self.stacked.indexOf(self.medical_records_screen)
        if idx != -1:
            self.display_screen(idx)

    # NEW: open Consent Forms with patient preselected (if supported)
    def _open_consent_for_patient(self, pid: int, pname: str):
        try:
            quick_create = getattr(self.consent_screen, "quick_create_for", None)
            if callable(quick_create):
                quick_create(pid, pname)
        except Exception as e:
            log_error(f"Consent quick_create_for failed: {e}")

        idx = self.stacked.indexOf(self.consent_screen)
        if idx != -1:
            self.display_screen(idx)

    def open_visit(self, visit_id: int):
        try:
            fn = getattr(self.medical_records_screen, "focus_on_visit", None)
            if callable(fn):
                fn(visit_id)
        except Exception as e:
            log_error(f"focus_on_visit failed: {e}")
        idx = self.stacked.indexOf(self.medical_records_screen)
        if idx != -1:
            self.display_screen(idx)

    def on_backup_now_clicked(self):
        try:
            path = backup_now()
            QMessageBox.information(self, "Backup complete", f"Backup saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Backup failed", str(e))

    def closeEvent(self, e):
        # Ask every child widget to shut down timers if they implement stop_timers()
        for w in self.findChildren(QWidget):
            stop = getattr(w, "stop_timers", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    pass
        super().closeEvent(e)

    def show_about_dialog(self):
        dlg = AboutDialog(self)
        dlg.exec()


