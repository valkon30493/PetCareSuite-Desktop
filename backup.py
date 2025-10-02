import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

APP_DIR_NAME = "PetCareSuite-Desktop"
DB_FILE_NAME = "vet_management.db"
RETENTION_DAYS = 14  # keep last 14 daily backups
ASSETS_DIR = "assets"  # bundled, read-only


def data_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or os.path.join(Path.home(), "AppData", "Local")
    p = Path(base) / APP_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    (p / "backups").mkdir(parents=True, exist_ok=True)
    (p / "logs").mkdir(parents=True, exist_ok=True)
    return p


def _base_dir() -> Path:
    """Folder where bundled read-only assets live (handles PyInstaller)."""
    if hasattr(sys, "_MEIPASS"):  # set by PyInstaller
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def resource_path(rel: str) -> Path:
    """Absolute path to a bundled resource (e.g., assets/style.qss)."""
    return _base_dir() / rel


DB_PATH = data_dir() / DB_FILE_NAME
BACKUP_DIR = data_dir() / "backups"
LOG_PATH = data_dir() / "logs" / "vet_management_errors.log"

STYLE_QSS = (
    Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    / "assets"
    / "style.qss"
)
LOGO_PNG = resource_path(f"{ASSETS_DIR}/app.ico")



def ensure_seed_db(seed_path: str | os.PathLike | None = None) -> None:
    if not DB_PATH.exists():
        if seed_path and Path(seed_path).exists():
            shutil.copy2(seed_path, DB_PATH)
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.close()


def _sqlite_backup(src: Path, dst: Path) -> None:
    with sqlite3.connect(src) as s, sqlite3.connect(dst) as d:
        s.backup(d)


def backup_now() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = BACKUP_DIR / f"vet_management-{ts}.db"
    _sqlite_backup(DB_PATH, dst)
    return dst


def _cleanup_old_backups() -> None:
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    for f in BACKUP_DIR.glob("vet_management-*.db"):
        try:
            dt = datetime.strptime(
                f.stem.replace("vet_management-", ""), "%Y%m%d_%H%M%S"
            )
            if dt < cutoff:
                f.unlink(missing_ok=True)
        except Exception:
            pass


def _marker_file() -> Path:
    return BACKUP_DIR / "last_daily_backup.txt"


def auto_daily_backup_if_needed() -> Path | None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    marker = _marker_file()
    today = datetime.now().strftime("%Y-%m-%d")
    last = marker.read_text().strip() if marker.exists() else ""
    if last != today:
        path = backup_now()
        marker.write_text(today, encoding="utf-8")
        _cleanup_old_backups()
        return path
    return None
