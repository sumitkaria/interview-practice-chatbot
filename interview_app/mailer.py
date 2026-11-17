"""Send contact-form messages through Gmail SMTP."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from interview_app import config

CONTACT_TO = "sumitfrm@gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


class MailError(Exception):
    """The contact message could not be emailed."""


def smtp_configured() -> bool:
    return bool(config.contact_smtp_user() and config.contact_smtp_password())


def send_contact_message(*, name: str, reply_email: str, subject: str, message: str) -> None:
    user = config.contact_smtp_user()
    password = config.contact_smtp_password()
    if not user or not password:
        raise MailError(
            "Contact email is not set up yet. Add CONTACT_SMTP_USER and CONTACT_SMTP_PASSWORD "
            "in Streamlit secrets (a Gmail App Password)."
        )

    cleaned_name = (name or "").strip() or "Anonymous"
    cleaned_email = (reply_email or "").strip()
    cleaned_subject = (subject or "").strip() or "Interview Practice concern"
    cleaned_message = (message or "").strip()
    if not cleaned_email:
        raise MailError("Please include an email so we can reply.")
    if not cleaned_message:
        raise MailError("Please describe your concern.")

    to_address = config.contact_to_email()
    mail = EmailMessage()
    mail["Subject"] = f"[Interview Practice] {cleaned_subject}"
    mail["From"] = f"Interview Practice <{user}>"
    mail["To"] = to_address
    mail["Reply-To"] = cleaned_email
    mail.set_content(
        "\n".join(
            [
                f"Name: {cleaned_name}",
                f"Reply-to: {cleaned_email}",
                f"Subject: {cleaned_subject}",
                "",
                cleaned_message,
            ]
        )
    )

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30) as smtp:
            smtp.login(user, password)
            smtp.send_message(mail)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(
            "Gmail rejected the SMTP login. Check CONTACT_SMTP_USER and the App Password in secrets."
        ) from exc
    except Exception as exc:
        raise MailError("The concern could not be emailed. Try again in a moment.") from exc
