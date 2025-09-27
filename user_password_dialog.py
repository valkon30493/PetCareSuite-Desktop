# user_password_dialog.py

import sqlite3
from hashlib import sha256
from PySide6.QtWidgets import ( QDialog, QFormLayout, QLineEdit, QPushButton, QMessageBox, QVBoxLayout
)
from db import connect as _connect

class ChangeMyPasswordDialog(QDialog):
    def __init__(self, username):
        super().__init__()
        self.setWindowTitle("Change My Password")
        self.username = username

        layout = QVBoxLayout()
        form = QFormLayout()

        self.old_pw = QLineEdit()
        self.old_pw.setEchoMode(QLineEdit.Password)

        self.new_pw = QLineEdit()
        self.new_pw.setEchoMode(QLineEdit.Password)

        self.confirm_pw = QLineEdit()
        self.confirm_pw.setEchoMode(QLineEdit.Password)

        form.addRow("Old Password:", self.old_pw)
        form.addRow("New Password:", self.new_pw)
        form.addRow("Confirm New Password:", self.confirm_pw)

        layout.addLayout(form)

        self.save_button = QPushButton("Change Password")
        self.save_button.clicked.connect(self.update_password)
        layout.addWidget(self.save_button)

        self.setLayout(layout)

    def update_password(self):
        old = self.old_pw.text().strip()
        new = self.new_pw.text().strip()
        confirm = self.confirm_pw.text().strip()

        if not (old and new and confirm):
            QMessageBox.warning(self, "Input Error", "All fields are required.")
            return

        if new != confirm:
            QMessageBox.warning(self, "Mismatch", "New passwords do not match.")
            return

        conn = _connect()
        cur = conn.cursor()
        hashed_old = sha256(old.encode()).hexdigest()
        cur.execute("SELECT user_id FROM users WHERE username=? AND password=?", (self.username, hashed_old))
        result = cur.fetchone()

        if not result:
            QMessageBox.critical(self, "Error", "Old password is incorrect.")
            conn.close()
            return

        new_hash = sha256(new.encode()).hexdigest()
        cur.execute("UPDATE users SET password=? WHERE username=?", (new_hash, self.username))
        conn.commit()
        conn.close()

        QMessageBox.information(self, "Success", "Password updated successfully.")
        self.accept()



