"""Email/password accounts and signed browser sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt

from interview_app import db

COOKIE_NAME = "ip_session"
SESSION_TTL_SECONDS = 30 * 24 * 3600
BCRYPT_MAX_BYTES = 72
LOGIN_FAILURE_LIMIT = 8
LOGIN_LOCK_SECONDS = 15 * 60
_DUMMY_HASH: str | None = None


class AuthError(Exception):
    """A sign-in or registration attempt was rejected."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def valid_email(email: str) -> bool:
    if not email or len(email) > 320 or any(character.isspace() for character in email):
        return False
    local, separator, domain = email.partition("@")
    if separator != "@" or "@" in domain or not local or not domain:
        return False
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        return False
    return "." in domain


def display_name(name: str, email: str) -> str:
    cleaned = " ".join(name.split()).strip()
    if cleaned:
        return cleaned[:80]
    return email.split("@", 1)[0][:80]


def hash_password(password: str, rounds: int = 12) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise AuthError("Use a shorter password.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("ascii"))
    except ValueError:
        return False


def _dummy_password_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("not-a-real-password")
    return _DUMMY_HASH


def make_session_token(
    user_id: str,
    secret: str,
    ttl_seconds: int = SESSION_TTL_SECONDS,
    now: int | None = None,
    session_id: str | None = None,
) -> str:
    issued = int(time.time() if now is None else now)
    payload: dict[str, str | int] = {"uid": user_id, "exp": issued + ttl_seconds}
    if session_id:
        payload["sid"] = session_id
    body = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode("ascii")
        .rstrip("=")
    )
    signature = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def _token_payload(token: str, secret: str, now: int | None = None, *, check_exp: bool = True) -> dict | None:
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if not isinstance(payload, dict):
            return None
        current = int(time.time() if now is None else now)
        if check_exp and int(payload["exp"]) < current:
            return None
        if not str(payload.get("uid") or ""):
            return None
        return payload
    except Exception:
        return None


def read_session_token(token: str, secret: str, now: int | None = None) -> str | None:
    payload = _token_payload(token, secret, now)
    if payload is None:
        return None
    return str(payload["uid"])


def open_session(user_id: str, secret: str, now: int | None = None) -> str:
    issued = int(time.time() if now is None else now)
    session_id = str(uuid.uuid4())
    expires = datetime.fromtimestamp(issued + SESSION_TTL_SECONDS, timezone.utc)
    db.create_login_session(session_id, user_id, expires)
    return make_session_token(user_id, secret, now=issued, session_id=session_id)


def authenticated_user_id(token: str, secret: str, now: int | None = None) -> str | None:
    payload = _token_payload(token, secret, now)
    if payload is None or not payload.get("sid"):
        return None
    issued = int(time.time() if now is None else now)
    current = datetime.fromtimestamp(issued, timezone.utc)
    user_id = str(payload["uid"])
    if not db.login_session_active(str(payload["sid"]), user_id, current):
        return None
    return user_id


def revoke_session_token(token: str, secret: str) -> None:
    payload = _token_payload(token, secret, check_exp=False)
    if payload and payload.get("sid"):
        db.revoke_login_session(str(payload["sid"]))


def register_user(name: str, email: str, password: str) -> db.UserRecord:
    email = normalize_email(email)
    if not valid_email(email):
        raise AuthError("Enter a valid email address.")
    if len(password) < 8:
        raise AuthError("Use at least 8 characters for the password.")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise AuthError("Use a shorter password.")
    try:
        return db.create_password_user(
            display_name(name, email),
            email,
            hash_password(password),
        )
    except db.EmailTaken as exc:
        raise AuthError("We couldn't create the account. Try logging in, or use another email.") from exc


def login_user(email: str, password: str) -> db.UserRecord:
    email = normalize_email(email)
    if db.login_locked(email):
        raise AuthError("Too many attempts. Try again in a few minutes.")
    user = db.get_user_by_email(email)
    password_ok = bool(user and user.password_hash and verify_password(password, user.password_hash))
    if not password_ok:
        if not (user and user.password_hash):
            verify_password(password, _dummy_password_hash())
        db.note_login_failure(email, limit=LOGIN_FAILURE_LIMIT, lock_seconds=LOGIN_LOCK_SECONDS)
        raise AuthError("Email or password is incorrect.")
    db.clear_login_failures(email)
    return user


def change_password(user_id: str, current_password: str, new_password: str) -> None:
    if len(new_password) < 8:
        raise AuthError("Use at least 8 characters for the password.")
    if len(new_password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise AuthError("Use a shorter password.")
    user = db.get_user(user_id)
    if user is None or not user.password_hash or not verify_password(current_password, user.password_hash):
        raise AuthError("The current password is incorrect.")
    db.set_password_hash(user_id, hash_password(new_password))
    db.revoke_user_sessions(user_id)


def request_password_reset(email: str) -> None:
    from interview_app import mailer

    if not mailer.configured():
        raise AuthError("Password reset by email is not set up yet. Change it from Account after you sign in.")
    user = db.get_user_by_email(normalize_email(email))
    if user is None or not user.password_hash:
        return
    token = _new_token()
    db.save_password_token(user.id, _token_hash(token), "reset", db.utcnow() + timedelta(hours=2))
    mailer.send_email(
        user.email,
        "Reset your Interview Practice password",
        "Use this link within two hours to choose a new password:\n\n"
        + mailer.app_link("reset", token)
        + "\n\nIf you did not ask for this, you can ignore it.\n",
    )


def reset_password(token: str, new_password: str) -> None:
    if len(new_password) < 8:
        raise AuthError("Use at least 8 characters for the password.")
    if len(new_password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise AuthError("Use a shorter password.")
    user_id = db.take_password_token(_token_hash(token), "reset")
    if not user_id:
        raise AuthError("That reset link has expired. Request a new one.")
    db.set_password_hash(user_id, hash_password(new_password))
    db.revoke_user_sessions(user_id)


def send_verification(user: db.UserRecord) -> None:
    from interview_app import mailer

    if not mailer.configured() or user.email_verified_at is not None:
        return
    token = _new_token()
    db.save_password_token(user.id, _token_hash(token), "verify", db.utcnow() + timedelta(days=2))
    mailer.send_email(
        user.email,
        "Confirm your Interview Practice email",
        "Confirm this email for Interview Practice:\n\n" + mailer.app_link("verify", token) + "\n",
    )


def confirm_verification(token: str) -> bool:
    user_id = db.take_password_token(_token_hash(token), "verify")
    if not user_id:
        return False
    db.mark_email_verified(user_id)
    return True


def _new_token() -> str:
    import secrets

    return secrets.token_urlsafe(32)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
