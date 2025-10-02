# prescriptions.py
import sqlite3

from db import connect as _connect


def get_prescriptions(patient_id=None):
    conn = _connect()
    cur = conn.cursor()
    if patient_id:
        cur.execute(
            """
          SELECT rx_id, patient_id, medication, dose, frequency,
                 quantity, start_date, end_date
            FROM prescriptions
           WHERE patient_id=?
        """,
            (patient_id,),
        )
    else:
        cur.execute(
            """
          SELECT rx_id, patient_id, medication, dose, frequency,
                 quantity, start_date, end_date
            FROM prescriptions
        """
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def create_rx(
    patient_id, medication, dose, frequency, quantity, start_date, end_date=None
):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
      INSERT INTO prescriptions
        (patient_id, medication, dose, frequency, quantity, start_date, end_date)
      VALUES (?,?,?,?,?,?,?)
    """,
        (patient_id, medication, dose, frequency, quantity, start_date, end_date),
    )
    conn.commit()
    conn.close()


def update_rx(rx_id, **fields):
    cols, vals = zip(*fields.items())
    set_clause = ", ".join(f"{col}=?" for col in cols)
    conn = _connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE prescriptions SET {set_clause} WHERE rx_id=?", (*vals, rx_id))
    conn.commit()
    conn.close()


def delete_rx(rx_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM prescriptions WHERE rx_id=?", (rx_id,))
    conn.commit()
    conn.close()
