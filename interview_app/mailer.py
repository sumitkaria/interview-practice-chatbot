"""Optional email for password reset and address confirmation."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from interview_app import config


def configured() -> bool:
    return config.smtp_settings() is not None


def app_link(kind: str, token: str) -> str:
    return f"{config.public_app_url()}/?{kind}={token}"


def send_email(recipient: str, subject: str, body: str) -> None:
    settings = config.smtp_settings()
    if settings is None:
        raise RuntimeError("Email is not configured.")
    message = EmailMessage()
    message["From"] = str(settings["from"])
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(str(settings["host"]), int(settings["port"]), timeout=20) as smtp:
        smtp.starttls()
        user = str(settings["user"] or "")
        if user:
            smtp.login(user, str(settings["password"] or ""))
        smtp.send_message(message)
