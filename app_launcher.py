# app_launcher.py
import db  # central DB gateway
import sys, os, traceback
from PySide6.QtWidgets import QApplication, QMessageBox
from login_screen import LoginWindow
from main_window import MainWindow
from logger import log_error
from updater import check_for_update, start_update_flow
from backup import ensure_seed_db, auto_daily_backup_if_needed, DB_PATH, STYLE_QSS  # central paths
from db import open_conn


# ---------- resource helper (works in dev and frozen) ----------
def resource_path(relative_path: str) -> str:
    """
    Return an absolute path to a resource bundled by PyInstaller.
    Falls back to the project directory in development.
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    # Use this file's folder (more reliable than CWD)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)





def required_tables() -> list[str]:
    # core tables needed before UI touches DB
    return [
        "roles", "users",
        "patients", "appointments",
        "invoices", "invoice_items", "payment_history",
        "items", "stock_movements",
        "reminders", "prescriptions"
    ]


def tables_present() -> set[str]:
    try:
        with open_conn() as con:
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            return {row[0] for row in cur.fetchall()}
    except Exception:
        return set()


def ensure_core_schema() -> None:
    """
    Make sure essential tables exist BEFORE any UI touches the DB.
    1) Run init_db.main() (idempotent, preferred).
    2) Re-check, then do a tiny emergency bootstrap for inventory tables if still missing.
    3) Final smoke test: assert all required tables exist; fail early if not.
    """
    must_have = required_tables()

    # First pass
    have = tables_present()
    need = [t for t in must_have if t not in have]

    if need:
        # 1) Preferred: run your initializer
        try:
            from init_db import main as init_db_main
            init_db_main()  # should use CREATE TABLE IF NOT EXISTS everywhere
        except Exception as e:
            log_error(f"init_db.main() failed: {e}")  # non-fatal for now

        # 2) Re-check what's still missing after init_db
        have = tables_present()
        need = [t for t in must_have if t not in have]

    # 3) Emergency fallback (keep minimal)
    try:
        if "items" in need:
            with open_conn() as con:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS items (
                      item_id            INTEGER PRIMARY KEY AUTOINCREMENT,
                      name               TEXT    NOT NULL,
                      description        TEXT,
                      unit_cost          REAL    NOT NULL DEFAULT 0,
                      unit_price         REAL    NOT NULL DEFAULT 0,
                      reorder_threshold  INTEGER NOT NULL DEFAULT 0
                    );
                """)
        if "stock_movements" in need:
            with open_conn() as con:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS stock_movements (
                      movement_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                      item_id      INTEGER NOT NULL,
                      change_qty   INTEGER NOT NULL,
                      reason       TEXT,
                      timestamp    TEXT    NOT NULL,
                      FOREIGN KEY (item_id) REFERENCES items(item_id)
                    );
                """)
    except Exception as e:
        log_error(f"Emergency inventory bootstrap failed: {e}")

    # 4) Final smoke test: fail early if anything is still missing
    have_final = tables_present()
    missing = [t for t in must_have if t not in have_final]
    if missing:
        msg = f"Fatal: missing required tables after init: {missing}"
        log_error(msg)
        raise RuntimeError(msg)

    # Optional: console debug
    try:
        print(f"ðŸâ€Å½ Using DB at: {DB_PATH}")
        print(f"🧱 Tables now present: {sorted(have_final)}")
    except Exception:
        pass


def launch_app():
    app = QApplication(sys.argv)

    # 1) Ensure DB file exists
    ensure_seed_db()  # creates empty DB if missing (or copies a seed)

    # 2) Ensure schema BEFORE creating any UI
    ensure_core_schema()

    # 3) Daily backup after schema is in place
    auto_daily_backup_if_needed()

    # 4) Styles –†prefer centralized STYLE_QSS; fallback to /style/style.qss
    applied_style = False
    for candidate in (str(STYLE_QSS), resource_path(os.path.join("style", "style.qss"))):
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
            applied_style = True
            break
        except Exception as e:
            print(f"Style not applied from {candidate}: {e}")
    if not applied_style:
        print("Running without styles.")

    # 5) Instantiate screens
    login_window = LoginWindow()
    main_window = MainWindow()

    # 6) Update check banner
    try:
        appcast = check_for_update()
        if appcast:
            m = QMessageBox()
            m.setWindowTitle("Update available")
            m.setText(f"PetWellnessApp {appcast['latest']} is available.\n\n{appcast.get('notes', '')}")
            m.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            if m.exec() == QMessageBox.Yes:
                start_update_flow(appcast)
    except Exception as e:
        # Non-fatal; log and continue
        log_error(f"Update check failed: {e}")

    def on_logged_in(username, role):
        main_window.set_user_context(username, role)
        main_window.showFullScreen()

    login_window.login_successful.connect(on_logged_in)

    try:
        login_window.show()
        sys.exit(app.exec())
    except Exception:
        err_trace = traceback.format_exc()
        print(err_trace)
        log_error(f"Application startup error:\n{err_trace}")
        QMessageBox.critical(
            login_window,
            "Startup Error",
            "An unexpected error occurred while launching the application.\n"
            "Please check the logs or console for details."
        )
        sys.exit(1)


if __name__ == "__main__":
    launch_app()
