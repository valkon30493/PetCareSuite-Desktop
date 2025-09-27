# notifications.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import sqlite3
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("python-dotenv not installed; skipping .env load")


smtp_email = os.getenv('SMTP_EMAIL')
smtp_password = os.getenv('SMTP_PASSWORD')
smtp_server = os.getenv('SMTP_SERVER', 'smtp.office365.com')
smtp_port = int(os.getenv('SMTP_PORT', 587))

# ðŸ‴ Global kill-switch (set ENABLE_EMAILS=0 in your .env to disable)
ENABLE_EMAILS = str(os.getenv("ENABLE_EMAILS", "0")).strip().lower() in ("1", "true", "yes")

def send_email(to_email, subject, message):
    """Send an email notification using SMTP (Outlook)."""
    try:
        if not smtp_email or not smtp_password:
            print("SMTP credentials not configured.")
            return False

        msg = MIMEMultipart()
        msg["From"] = smtp_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_email, smtp_password)
        server.send_message(msg)
        server.quit()

        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

