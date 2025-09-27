# user_management.py

import sqlite3
from hashlib import sha256
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QComboBox, QLabel, QMessageBox, QFormLayout, QInputDialog
)
from db import connect as _connect

class UserManagementScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("User Management")

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Table to list users
        self.user_table = QTableWidget()
        self.user_table.setColumnCount(2)
        self.user_table.setHorizontalHeaderLabels(["Username", "Role"])
        layout.addWidget(self.user_table)

        # Form to add a new user
        form = QFormLayout()
        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)

        self.role_dropdown = QComboBox()
        self.load_roles()

        form.addRow("Username:", self.username_input)
        form.addRow("Password:", self.password_input)
        form.addRow("Role:", self.role_dropdown)
        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        self.add_button = QPushButton("Add User")
        self.delete_button = QPushButton("Delete Selected User")
        self.change_pw_button = QPushButton("Change Password")

        btn_layout.addWidget(self.add_button)
        btn_layout.addWidget(self.delete_button)
        btn_layout.addWidget(self.change_pw_button)
        layout.addLayout(btn_layout)

        # Signals
        self.add_button.clicked.connect(self.add_user)
        self.delete_button.clicked.connect(self.delete_selected_user)
        self.change_pw_button.clicked.connect(self.change_password)

        self.load_users()

    def load_roles(self):
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("SELECT role_name FROM roles")
        roles = cursor.fetchall()
        conn.close()

        self.role_dropdown.clear()
        for role in roles:
            self.role_dropdown.addItem(role[0])

    def load_users(self):
        self.user_table.setRowCount(0)
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT username, role_name
            FROM users
            JOIN roles ON users.role_id = roles.role_id
        ''')
        users = cursor.fetchall()
        conn.close()

        for row_idx, (username, role) in enumerate(users):
            self.user_table.insertRow(row_idx)
            self.user_table.setItem(row_idx, 0, QTableWidgetItem(username))
            self.user_table.setItem(row_idx, 1, QTableWidgetItem(role))

    def add_user(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        role = self.role_dropdown.currentText()

        if not username or not password:
            QMessageBox.warning(self, "Input Error", "Username and password are required.")
            return

        hashed = sha256(password.encode()).hexdigest()

        conn = _connect()
        cursor = conn.cursor()

        # Get role ID
        cursor.execute("SELECT role_id FROM roles WHERE role_name = ?", (role,))
        result = cursor.fetchone()
        if not result:
            QMessageBox.critical(self, "Error", "Selected role not found.")
            conn.close()
            return

        role_id = result[0]

        try:
            cursor.execute('''
                INSERT INTO users (username, password, role_id)
                VALUES (?, ?, ?)
            ''', (username, hashed, role_id))
            conn.commit()
            QMessageBox.information(self, "Success", f"User '{username}' created.")
            self.load_users()
            self.username_input.clear()
            self.password_input.clear()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Error", "Username already exists.")
        finally:
            conn.close()

    def delete_selected_user(self):
        row = self.user_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Select a user to delete.")
            return

        username = self.user_table.item(row, 0).text()
        if username == "admin":
            QMessageBox.warning(self, "Not Allowed", "You cannot delete the default admin.")
            return

        confirm = QMessageBox.question(self, "Confirm Deletion",
                                       f"Delete user '{username}'?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm != QMessageBox.StandardButton.Yes:
            return

        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        conn.close()

        QMessageBox.information(self, "Deleted", f"User '{username}' has been deleted.")
        self.load_users()

    def change_password(self):
        row = self.user_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Select a user to change password.")
            return

        username = self.user_table.item(row, 0).text()
        if not username:
            return

        # Ask for new password
        new_pw, ok = QInputDialog.getText(self, "Change Password",
                                          f"Enter new password for '{username}':",
                                          QLineEdit.Password)
        if not ok or not new_pw.strip():
            return

        hashed_pw = sha256(new_pw.encode()).hexdigest()

        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password = ? WHERE username = ?", (hashed_pw, username))
        conn.commit()
        conn.close()

        QMessageBox.information(self, "Success", f"Password for '{username}' updated.")



