import logging
import sqlite3
import os
from backup import LOG_PATH
from db import connect as _connect

# Set up logging to a file
LOG_FILE = str(LOG_PATH)
logging.basicConfig(filename=LOG_FILE, level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

# Ensure the error log table exists in the database
def setup_error_logging():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS error_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            error_type TEXT,
            error_message TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Call setup function at the start
setup_error_logging()

def log_error(error_message: str, error_type: str = "General"):
    """Log errors to both a file and the database for debugging."""
    logging.error(error_message)

    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO error_logs (timestamp, error_type, error_message) "
            "VALUES (datetime('now'), ?, ?)",
            (error_type, error_message)
        )
        conn.commit()
    except Exception as e:
        # Don’t crash the app if logging fails; record why.
        logging.exception(f"log_error DB insert failed: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass




