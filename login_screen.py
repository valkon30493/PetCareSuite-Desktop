# login_screen.py
from hashlib import sha256

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backup import resource_path
from db import connect as _connect


class LoginWindow(QMainWindow):
    login_successful = Signal(str, str)  # username, role

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login - PetCareSuite Desktop")
        self.setFixedSize(400, 280)  # compact and consistent

        # Widgets
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)

        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self.authenticate_user)

        # Layout
        layout = QVBoxLayout()
        logo = QLabel()
        pix = QPixmap(resource_path("assets/petcaresuite_icon_512.png"))
        if not pix.isNull():
            logo.setPixmap(pix.scaledToHeight(80, Qt.SmoothTransformation))
            logo.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo)
        layout.addWidget(QLabel("Please log in"))
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def authenticate_user(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        hashed_password = sha256(password.encode()).hexdigest()

        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT users.user_id, roles.role_name
            FROM users
            JOIN roles ON users.role_id = roles.role_id
            WHERE users.username = ? AND users.password = ?
        """,
            (username, hashed_password),
        )
        user = cursor.fetchone()
        conn.close()

        if user:
            user_id, role_name = user
            self.login_successful.emit(username, role_name)
            self.close()
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid username or password")
