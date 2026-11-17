"""Runtime settings from the environment or Streamlit secrets."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "grok-4.7"
DEFAULT_EFFORT = "low"
ALLOWED_EFFORTS = {"low", "medium", "high", "xhigh"}
XAI_BASE_URL = "https://api.x.ai/v1"


def secret(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        if name in st.secrets:
            found = st.secrets[name]
            if found:
                return str(found)
    except Exception:
        pass
    return default


def xai_api_key() -> str | None:
    key = secret("XAI_API_KEY")
    return key.strip() if key else None


def grok_model() -> str:
    model = secret("GROK_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
    return model.strip() or DEFAULT_MODEL


def grok_effort() -> str:
    effort = (secret("GROK_REASONING_EFFORT", DEFAULT_EFFORT) or DEFAULT_EFFORT).strip().lower()
    if effort not in ALLOWED_EFFORTS:
        return DEFAULT_EFFORT
    return effort


def data_dir() -> Path:
    path = ROOT / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


class DatabaseURLError(ValueError):
    """DATABASE_URL is present but is not a usable Postgres address."""


def normalize_database_url(url: str) -> str:
    cleaned = url.strip()
    if cleaned.startswith("postgres://"):
        cleaned = "postgresql://" + cleaned[len("postgres://") :]
    if cleaned.startswith("postgresql+psycopg://"):
        return cleaned
    if cleaned.startswith("postgresql://"):
        return "postgresql+psycopg://" + cleaned[len("postgresql://") :]
    return cleaned


def _postgres_candidates(text: str) -> list[str]:
    markers = ("postgresql+psycopg://", "postgresql://", "postgres://")
    found: list[str] = []
    start = 0
    lowered = text.lower()
    while start < len(text):
        positions = [lowered.find(marker, start) for marker in markers]
        positions = [pos for pos in positions if pos >= 0]
        if not positions:
            break
        begin = min(positions)
        end = begin
        while end < len(text) and text[end] not in " \t\r\n\"'":
            end += 1
        candidate = text[begin:end].rstrip(".,);")
        if candidate:
            found.append(candidate)
        start = max(end, begin + 1)
    return found


def _host_labels_ok(host: str) -> bool:
    if not host or any(char.isspace() for char in host):
        return False
    labels = host.split(".")
    if labels[-1] == "":
        labels = labels[:-1]
    return bool(labels) and all(labels)


def prepare_database_url(raw: str) -> str:
    """Turn a Streamlit secret into a driver URL, or explain why it cannot connect."""
    text = raw.strip().strip('"').strip("'").strip()
    candidates = _postgres_candidates(text) or [text]
    usable: list[str] = []
    saw_dotted_host = False
    for candidate in candidates:
        normalized = normalize_database_url(candidate)
        try:
            from sqlalchemy.engine.url import make_url

            parsed = make_url(normalized)
        except Exception:
            continue
        host = parsed.host or ""
        if host.startswith(".") or ".." in host:
            saw_dotted_host = True
            stripped = host.lstrip(".")
            if parsed.username and parsed.password and _host_labels_ok(stripped):
                normalized = parsed.set(host=stripped).render_as_string(hide_password=False)
                host = stripped
            else:
                continue
        if _host_labels_ok(host) and "." in host:
            usable.append(normalized)
    if usable:
        return usable[-1]
    if saw_dotted_host:
        raise DatabaseURLError(
            "DATABASE_URL still contains the sample dots, so the database address starts with a period. "
            "In Streamlit secrets, replace the whole DATABASE_URL value with the line from Neon. "
            "Open the Neon project, click Connect, and copy the line that starts with postgresql://. "
            "Paste that entire line between the quotes, save, and reboot."
        )
    raise DatabaseURLError(
        "DATABASE_URL is not a complete Postgres connection string. "
        "Open the Neon project, click Connect, and copy the line that starts with postgresql://. "
        "Paste that entire line between the quotes in Streamlit secrets, save, and reboot."
    )


def database_url() -> str:
    configured = secret("DATABASE_URL")
    if configured:
        return prepare_database_url(configured)
    path = data_dir() / "interview.db"
    return "sqlite:///" + path.resolve().as_posix()


def uses_local_sqlite() -> bool:
    return database_url().startswith("sqlite")


def on_streamlit_cloud() -> bool:
    return Path("/mount/src").is_dir()


def _positive_int(name: str, default: int) -> int:
    raw = secret(name)
    if not raw:
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        return default
    return value if value > 0 else default


def max_interviews_per_day() -> int:
    return _positive_int("MAX_INTERVIEWS_PER_DAY", 6)


def max_model_calls_per_day() -> int:
    return _positive_int("MAX_MODEL_CALLS_PER_DAY", 160)


def public_app_url() -> str:
    value = (secret("PUBLIC_APP_URL") or "https://interviewpractice.streamlit.app").strip()
    return value.rstrip("/") or "https://interviewpractice.streamlit.app"


def contact_email() -> str:
    value = (secret("CONTACT_EMAIL") or "sumitkaria11@gmail.com").strip()
    return value or "sumitkaria11@gmail.com"


def admin_emails() -> set[str]:
    raw = secret("ADMIN_EMAILS") or ""
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def is_admin(email: str) -> bool:
    allowed = admin_emails()
    if not allowed:
        allowed = {contact_email().lower()}
    return email.strip().lower() in allowed


def smtp_settings() -> dict[str, str | int] | None:
    host = secret("SMTP_HOST")
    sender = secret("SMTP_FROM")
    if not host or not sender:
        return None
    port_text = secret("SMTP_PORT") or "587"
    try:
        port = int(port_text)
    except ValueError:
        port = 587
    return {
        "host": host.strip(),
        "port": port,
        "user": (secret("SMTP_USER") or "").strip(),
        "password": secret("SMTP_PASSWORD") or "",
        "from": sender.strip(),
    }


def cloud_config_problem() -> str | None:
    if not on_streamlit_cloud():
        return None
    if not secret("DATABASE_URL"):
        return (
            "This app is on Streamlit Cloud without DATABASE_URL. "
            "Add the Neon connection string in secrets, save, and reboot. "
            "Accounts are not kept on the Cloud machine."
        )
    if not secret("AUTH_COOKIE_SECRET"):
        return (
            "Add AUTH_COOKIE_SECRET in Streamlit secrets, save, and reboot. "
            "Without it, password sign-in is tied to a file that disappears on restart."
        )
    return None


def neon_direct_connection() -> bool:
    raw = secret("DATABASE_URL") or ""
    return ".neon.tech" in raw and "-pooler" not in raw


def auth_cookie_secret_is_configured() -> bool:
    return bool(secret("AUTH_COOKIE_SECRET"))


def auth_cookie_secret() -> str:
    configured = secret("AUTH_COOKIE_SECRET")
    if configured:
        return configured.strip()
    path = data_dir() / "cookie_secret"
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    value = secrets.token_hex(32)
    path.write_text(value, encoding="utf-8")
    path.chmod(0o600)
    return value


def google_auth_configured() -> bool:
    try:
        import streamlit as st

        auth = st.secrets["auth"]
    except Exception:
        return False
    required = (
        "redirect_uri",
        "cookie_secret",
        "client_id",
        "client_secret",
        "server_metadata_url",
    )
    try:
        return all(bool(auth.get(key)) for key in required)
    except Exception:
        return False
