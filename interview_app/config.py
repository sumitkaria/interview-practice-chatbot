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


def normalize_database_url(url: str) -> str:
    cleaned = url.strip()
    if cleaned.startswith("postgres://"):
        cleaned = "postgresql://" + cleaned[len("postgres://") :]
    if cleaned.startswith("postgresql+psycopg://"):
        return cleaned
    if cleaned.startswith("postgresql://"):
        return "postgresql+psycopg://" + cleaned[len("postgresql://") :]
    return cleaned


def database_url() -> str:
    configured = secret("DATABASE_URL")
    if configured:
        return normalize_database_url(configured)
    path = data_dir() / "interview.db"
    return "sqlite:///" + path.resolve().as_posix()


def uses_local_sqlite() -> bool:
    return database_url().startswith("sqlite")


def on_streamlit_cloud() -> bool:
    return Path("/mount/src").is_dir()


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
