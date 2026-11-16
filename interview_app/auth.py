"""Email/password accounts and signed browser sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time

import bcrypt

from interview_app import db

COOKIE_NAME = "ip_session"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SESSION_TTL_SECONDS = 30 * 24 * 3600


class AuthError(Exception):
    """A sign-in or registration attempt was rejected."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def valid_email(email: str) -> bool:
    return bool(_EMAIL.fullmatch(email))


def display_name(name: str, email: str) -> str:
    cleaned = " ".join(name.split()).strip()
    if cleaned:
        return cleaned[:80]
    return email.split("@", 1)[0][:80]


def _password_material(password: str) -> bytes:
    # bcrypt only uses the first 72 bytes. Hashing first keeps longer passwords intact.
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(_password_material(password), bcrypt.gensalt(rounds=rounds)).decode(
        "ascii"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_password_material(password), password_hash.encode("ascii"))
    except ValueError:
        return False


def make_session_token(
    user_id: str,
    secret: str,
    ttl_seconds: int = SESSION_TTL_SECONDS,
    now: int | None = None,
) -> str:
    issued = int(time.time() if now is None else now)
    payload = {"uid": user_id, "exp": issued + ttl_seconds}
    body = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode("ascii")
        .rstrip("=")
    )
    signature = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def read_session_token(token: str, secret: str, now: int | None = None) -> str | None:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        current = int(time.time() if now is None else now)
        if int(payload["exp"]) < current:
            return None
        user_id = str(payload["uid"])
        return user_id or None
    except Exception:
        return None


def register_user(name: str, email: str, password: str) -> db.UserRecord:
    email = normalize_email(email)
    if not valid_email(email):
        raise AuthError("Enter a valid email address.")
    if len(password) < 8:
        raise AuthError("Use at least 8 characters for the password.")
    if len(password) > 200:
        raise AuthError("Use a shorter password.")
    try:
        return db.create_password_user(
            display_name(name, email),
            email,
            hash_password(password),
        )
    except db.EmailTaken as exc:
        raise AuthError("An account with that email already exists. Log in instead.") from exc


def login_user(email: str, password: str) -> db.UserRecord:
    email = normalize_email(email)
    user = db.get_user_by_email(email)
    if user is None or not user.password_hash:
        if user is not None and not user.password_hash:
            raise AuthError("This email uses Google sign-in.")
        raise AuthError("Email or password is incorrect.")
    if not verify_password(password, user.password_hash):
        raise AuthError("Email or password is incorrect.")
    return user
