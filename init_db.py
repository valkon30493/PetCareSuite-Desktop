# init_db.py
from hashlib import sha256

from db import connect as _connect


# --- migrations helpers (ADD THIS BLOCK) ---
def _ensure_schema_version_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL
        )
    """
    )
    cur = conn.execute("SELECT version FROM schema_version WHERE id=1")
    if cur.fetchone() is None:
        conn.execute("INSERT INTO schema_version (id, version) VALUES (1, 1)")


def _get_version(conn) -> int:
    cur = conn.execute("SELECT version FROM schema_version WHERE id=1")
    row = cur.fetchone()
    return int(row[0]) if row else 1


def _set_version(conn, v: int):
    conn.execute("UPDATE schema_version SET version=? WHERE id=1", (v,))


def _migrate(conn):
    _ensure_schema_version_table(conn)
    v = _get_version(conn)

    # --- BEGIN PATCH: init_db._migrate additions ---
    # Find: def _migrate(conn): ... v = _get_version(conn)
    # Add the block below right after computing `v`.
    if v < 2:
        # Add owner snapshot columns for owner‑first invoicing
        conn.execute("ALTER TABLE invoices ADD COLUMN owner_name TEXT")
        conn.execute("ALTER TABLE invoices ADD COLUMN owner_contact TEXT")
        conn.execute("ALTER TABLE invoices ADD COLUMN owner_email TEXT")
        _set_version(conn, 2)

    # --- END PATCH ---


    # example future migration:
    # if v < 2:
    #     conn.execute("ALTER TABLE invoices ADD COLUMN notes TEXT DEFAULT NULL")
    #     _set_version(conn, 2)


def main():
    conn = _connect()
    cursor = conn.cursor()

    # Always enforce FKs
    cursor.execute("PRAGMA foreign_keys = ON;")

    # -----------------------------
    # Roles & Users
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS roles (
        role_id    INTEGER PRIMARY KEY,
        role_name  TEXT NOT NULL UNIQUE
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        user_id   INTEGER PRIMARY KEY,
        username  TEXT NOT NULL UNIQUE,
        password  TEXT NOT NULL,
        role_id   INTEGER,
        FOREIGN KEY (role_id) REFERENCES roles(role_id)
    )
    """
    )

    # -----------------------------
    # Patients
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS patients (
        patient_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        species       TEXT NOT NULL,
        breed         TEXT,
        age_years     INTEGER DEFAULT 0,
        age_months    INTEGER DEFAULT 0,
        owner_name    TEXT NOT NULL,
        owner_contact TEXT,
        owner_email   TEXT
    )
    """
    )

    # -----------------------------
    # Appointments
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS appointments (
        appointment_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id          INTEGER NOT NULL,
        date_time           TEXT NOT NULL,
        reason              TEXT NOT NULL,
        veterinarian        TEXT NOT NULL,
        status              TEXT NOT NULL,
        notification_status TEXT DEFAULT 'Not Sent',
        appointment_type    TEXT DEFAULT 'General',
        duration_minutes    INTEGER NOT NULL DEFAULT 30,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
    )
    """
    )

    # -----------------------------
    # Reminders
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS reminders (
        reminder_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_id  INTEGER,
        reminder_time   TEXT NOT NULL,
        reminder_status TEXT DEFAULT 'Pending',
        reminder_reason TEXT,
        FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id)
    )
    """
    )

    # -----------------------------
    # Invoices (supports INVOICE / ESTIMATE / CHARITY)
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS invoices (
        invoice_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_date       TEXT NOT NULL,
        appointment_id     INTEGER,  -- may be NULL for standalone docs
        patient_id         INTEGER,

        -- NEW: doc type
        invoice_type       TEXT NOT NULL CHECK (invoice_type IN ('INVOICE','ESTIMATE','CHARITY')) DEFAULT 'INVOICE',

        -- Money fields
        total_amount       REAL NOT NULL DEFAULT 0,
        tax                REAL NOT NULL DEFAULT 0,
        discount           REAL NOT NULL DEFAULT 0,
        final_amount       REAL NOT NULL DEFAULT 0,

        -- Payment
        payment_status     TEXT NOT NULL CHECK (payment_status IN ('Paid','Unpaid','Partially Paid','N/A')) DEFAULT 'Unpaid',
        payment_method     TEXT,
        created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        remaining_balance  REAL NOT NULL DEFAULT 0,

        -- Behavior flags
        payable            INTEGER NOT NULL DEFAULT 1,  -- 0 for ESTIMATE/CHARITY
        revenue_eligible   INTEGER NOT NULL DEFAULT 1,  -- 0 for ESTIMATE/CHARITY
        inventory_deducted INTEGER NOT NULL DEFAULT 0,  -- 1 after stock deduction for INVOICE/CHARITY

        -- Optional external numbers
        estimate_number    TEXT,
        charity_number     TEXT,

        FOREIGN KEY (appointment_id) REFERENCES appointments(appointment_id),
        FOREIGN KEY (patient_id)    REFERENCES patients(patient_id)
    )
    """
    )

    # One document per (appointment_id, invoice_type); allows all three per appointment
    # appointment_id can be NULL, so we make it a partial unique index.
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_invoices_appt_type
        ON invoices(appointment_id, invoice_type)
        WHERE appointment_id IS NOT NULL
    """
    )

    # Helpful filters
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoices_type ON invoices(invoice_type)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoices_created ON invoices(created_at)"
    )

    # -----------------------------
    # Payment History
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS payment_history (
        payment_id     INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id     INTEGER NOT NULL,
        payment_date   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        amount_paid    REAL NOT NULL,
        payment_method TEXT,
        notes          TEXT,
        FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id) ON DELETE CASCADE
    )
    """
    )

    # -----------------------------
    # Invoice Items
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS invoice_items (
        item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id      INTEGER,
        description     TEXT NOT NULL,
        quantity        INTEGER NOT NULL,
        unit_price      REAL NOT NULL,
        total_price     REAL NOT NULL,

        -- Extras for breakdown
        vat_pct         REAL NOT NULL DEFAULT 0,
        vat_amount      REAL NOT NULL DEFAULT 0,
        vat_flag        TEXT NOT NULL DEFAULT '',
        discount_pct    REAL NOT NULL DEFAULT 0,
        discount_amount REAL NOT NULL DEFAULT 0,

        FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id) ON DELETE CASCADE
    )
    """
    )

    # -----------------------------
    # Inventory
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS items (
      item_id            INTEGER PRIMARY KEY AUTOINCREMENT,
      name               TEXT NOT NULL,
      description        TEXT,
      unit_cost          REAL NOT NULL DEFAULT 0,
      unit_price         REAL NOT NULL DEFAULT 0,
      reorder_threshold  INTEGER NOT NULL DEFAULT 0
    )
    """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_name ON items(name)")

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS stock_movements (
      movement_id INTEGER PRIMARY KEY AUTOINCREMENT,
      item_id     INTEGER NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
      change_qty  INTEGER NOT NULL,
      reason      TEXT,
      timestamp   TEXT NOT NULL
    )
    """
    )

    # -----------------------------
    # Prescriptions
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS prescriptions (
      prescription_id INTEGER PRIMARY KEY AUTOINCREMENT,
      patient_id      INTEGER NOT NULL REFERENCES patients(patient_id),
      medication      TEXT NOT NULL,
      dosage          TEXT NOT NULL,
      instructions    TEXT,
      date_issued     TEXT NOT NULL,
      status          TEXT NOT NULL DEFAULT 'New',
      dispensed       INTEGER NOT NULL DEFAULT 0,
      date_dispensed  TEXT
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS prescription_history (
        history_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        prescription_id  INTEGER NOT NULL REFERENCES prescriptions(prescription_id) ON DELETE CASCADE,
        user_id          INTEGER,
        action           TEXT NOT NULL,
        timestamp        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        changes_json     TEXT
    )
    """
    )

    # -----------------------------
    # Consents (simple) + Templates/Forms
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS consents (
        consent_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id   INTEGER NOT NULL REFERENCES patients(patient_id),
        consent_type TEXT NOT NULL,
        notes        TEXT,
        signer_name  TEXT,
        signed_on    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        valid_until  TEXT,
        file_path    TEXT
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS consent_templates (
      template_id INTEGER PRIMARY KEY AUTOINCREMENT,
      name        TEXT NOT NULL UNIQUE,
      body_text   TEXT NOT NULL
    )
    """
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS consent_forms (
      consent_id      INTEGER PRIMARY KEY AUTOINCREMENT,
      patient_id      INTEGER NOT NULL REFERENCES patients(patient_id),
      template_id     INTEGER,
      form_type       TEXT NOT NULL,
      body_text       TEXT NOT NULL,
      signed_by       TEXT,
      relation        TEXT,
      signature_path  TEXT,
      status          TEXT NOT NULL DEFAULT 'Draft',
      follow_up_date  TEXT,
      created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (template_id) REFERENCES consent_templates(template_id)
    )
    """
    )

    cursor.execute(
        "INSERT OR IGNORE INTO consent_templates (name, body_text) VALUES (?, ?)",
        (
            "General Treatment Consent",
            "I, {owner_name}, consent to examination and treatment for {patient_name}...",
        ),
    )
    cursor.execute(
        "INSERT OR IGNORE INTO consent_templates (name, body_text) VALUES (?, ?)",
        (
            "Surgery Consent",
            "I, {owner_name}, authorize surgical procedure for {patient_name} on {date}...",
        ),
    )

    # -----------------------------
    # Visits
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS visits (
        visit_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id          INTEGER NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
        appointment_id      INTEGER REFERENCES appointments(appointment_id),
        visit_date          TEXT NOT NULL DEFAULT CURRENT_DATE,
        on_call             INTEGER NOT NULL DEFAULT 0,
        weight_kg           REAL,
        body_score          TEXT,
        temperature_c       REAL,
        heart_rate_bpm      INTEGER,
        resp_rate_bpm       INTEGER,
        mucosa_crt          TEXT,
        thorax_eval         TEXT,
        lymph_nodes         TEXT,
        palpation_abdomen   TEXT,
        ears_eyes_mouth     TEXT,
        skin_coat           TEXT,
        reproductive        TEXT,
        clinic_notes        TEXT,
        reason_admission    TEXT,
        tests_procedures    TEXT,
        findings            TEXT,
        diagnosis           TEXT,
        treatment           TEXT,
        notes               TEXT,
        created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS visit_attachments (
        attach_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        visit_id    INTEGER NOT NULL REFERENCES visits(visit_id) ON DELETE CASCADE,
        file_path   TEXT NOT NULL,
        note        TEXT,
        added_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """
    )

    cursor.execute(
        """
    CREATE INDEX IF NOT EXISTS idx_visits_patient_date
    ON visits(patient_id, visit_date)
    """
    )
    cursor.execute(
        """
    CREATE INDEX IF NOT EXISTS idx_visits_appt
    ON visits(appointment_id)
    """
    )
    cursor.execute(
        """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_visits_appt
    ON visits(appointment_id)
    WHERE appointment_id IS NOT NULL
    """
    )

    # -----------------------------
    # Error Logs
    # -----------------------------
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS error_logs (
        log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        error_type    TEXT,
        error_message TEXT NOT NULL
    )
    """
    )

    # Seed roles and a few users
    for role in ("Admin", "Veterinarian", "Receptionist"):
        cursor.execute("INSERT OR IGNORE INTO roles (role_name) VALUES (?)", (role,))

    def create_user(username: str, password: str, role_name: str):
        hashed = sha256(password.encode()).hexdigest()
        cursor.execute("SELECT role_id FROM roles WHERE role_name=?", (role_name,))
        row = cursor.fetchone()
        if not row:
            return
        role_id = row[0]
        cursor.execute(
            "INSERT OR IGNORE INTO users (username, password, role_id) VALUES (?, ?, ?)",
            (username, hashed, role_id),
        )

    create_user("admin", "admin123", "Admin")
    create_user("vetuser", "vet123", "Veterinarian")
    create_user("reception", "recep123", "Receptionist")

    # run migrations LAST so they can rely on base tables existing
    _migrate(conn)

    conn.commit()
    conn.close()

    # avoid mojibake in frozen/redirected output
    try:
        print("✅ Database initialized successfully.")
    except Exception:
        print("Database initialized successfully.")


if __name__ == "__main__":
    main()
