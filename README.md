# PetCareSuite

Modern veterinary clinic management — Desktop app (PySide6, SQLite) with clean architecture and upgrade path to Cloud/Pro tiers.

## Quick Start
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app_launcher.py
```

First run initializes the database and shows the login screen.

## Project Layout (key files)
- `app_launcher.py` — entry point
- `init_db.py` — schema creation & migrations
- `db.py` — DB connector/PRAGMAs
- `billing_invoicing.py`, `reports.py`, `reports_analytics.py`
- `appointment_scheduling.py`, `daily_appointments_calendar.py`
- `patient_management.py`, `medical_records.py`, `prescriptions.py` (+ GUI modules)
- `inventory.py`, `inventory_management.py`
- `consent_forms.py`, `consent_dialog.py`
- `user_management.py`, `login_screen.py`
- `notifications.py`, `notifications_reminders.py`
- `logger.py`, `error_log_viewer.py`
- `clinic_constants.py`
- `assets/` — `style.qss`, `pet_wellness_logo.png`

## Configuration
Copy `.env.example` to `.env` and edit as needed.

## Packaging
PyInstaller spec will be added; for now:
```bash
pip install pyinstaller
pyinstaller --noconsole --name PetCareSuite app_launcher.py
```

## Contributing
- Branch off `main` using `feat/*`, `fix/*`, `chore/*`
- Use Conventional Commits (e.g., `feat: add estimate invoices`)
- Open a PR; CI must pass

## License
Proprietary — All rights reserved. (Replace with your chosen license if needed.)
