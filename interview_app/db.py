"""Per-user accounts, saved materials, and interview sessions."""

from __future__ import annotations

import contextvars
import json
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text, func, inspect, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

_engine = None
_factory = None
_actor: contextvars.ContextVar[str | None] = contextvars.ContextVar("interview_actor", default=None)
_script_locks: dict[str, threading.Lock] = {}
_script_locks_guard = threading.Lock()
STORAGE_CAP_BYTES = 25 * 1024 * 1024
REPLACED_INTERVIEW_DAYS = 90
EVENT_RETENTION_DAYS = 30
APP_TIMEZONE = ZoneInfo("America/Edmonton")


class EmailTaken(Exception):
    """An account with this email already exists."""


class AuthLinkError(Exception):
    """A Google account could not be linked to the email."""


class QuotaExceeded(Exception):
    """This account has used its practice allowance for today."""


class NotOwner(Exception):
    """The signed-in account does not own that interview."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    job_description: Mapped[str] = mapped_column(Text, default="")
    job_source: Mapped[str] = mapped_column(String(300), default="")
    resume_text: Mapped[str] = mapped_column(Text, default="")
    resume_source: Mapped[str] = mapped_column(String(300), default="")
    job_file_id: Mapped[str] = mapped_column(String(36), default="")
    resume_file_id: Mapped[str] = mapped_column(String(36), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    job_description: Mapped[str] = mapped_column(Text, default="")
    resume_text: Mapped[str] = mapped_column(Text, default="")
    questions_json: Mapped[str] = mapped_column(Text, default="[]")
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    interview_id: Mapped[str] = mapped_column(ForeignKey("interviews.id"), index=True)
    question_index: Mapped[int] = mapped_column(Integer)
    question_text: Mapped[str] = mapped_column(Text, default="")
    transcript: Mapped[str] = mapped_column(Text, default="")
    model_answer: Mapped[str] = mapped_column(Text, default="")
    guidance: Mapped[str] = mapped_column(Text, default="")
    stop_reason: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginSession(Base):
    __tablename__ = "login_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginGuard(Base):
    __tablename__ = "login_guards"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StoredFile(Base):
    __tablename__ = "stored_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="")
    filename: Mapped[str] = mapped_column(String(300), default="")
    content_type: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AppEvent(Base):
    __tablename__ = "app_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), default="", index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    message: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ContactMessage(Base):
    __tablename__ = "contact_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reply_email: Mapped[str] = mapped_column(String(320), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(20), default="reset")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True)
class StoredFileInfo:
    id: str
    kind: str
    filename: str
    created_at: datetime


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str
    name: str
    password_hash: str | None
    google_sub: str | None
    email_verified_at: datetime | None = None


@dataclass(frozen=True)
class ProfileRecord:
    user_id: str
    job_description: str
    job_source: str
    resume_text: str
    resume_source: str
    updated_at: datetime
    job_file_id: str = ""
    resume_file_id: str = ""


@dataclass(frozen=True)
class InterviewRecord:
    id: str
    user_id: str
    job_description: str
    resume_text: str
    questions: tuple[str, ...]
    current_index: int
    status: str
    created_at: datetime
    interviewer_name: str = ""
    interviewer_title: str = ""
    introduction: str = ""
    bridges: dict[int, str] | None = None
    role_name: str = ""
    job_source: str = ""
    resume_source: str = ""
    role_brief: str = ""
    brief_done: bool = True
    mic_checked: bool = True
    chat_done: bool = True
    chat_wrap: bool = False
    chat_started_at: str = ""
    chat_log: tuple[tuple[str, str], ...] = ()
    job_file_id: str = ""
    resume_file_id: str = ""


@dataclass(frozen=True)
class TurnRecord:
    id: str
    interview_id: str
    question_index: int
    question_text: str
    transcript: str
    model_answer: str
    guidance: str
    stop_reason: str


def init_db(url: str | None = None, force: bool = False) -> None:
    global _engine, _factory
    if _factory is not None and not force:
        return
    if url is None:
        from interview_app.config import database_url

        url = database_url()
    if _engine is not None:
        _engine.dispose()
    from sqlalchemy import create_engine

    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=3,
            max_overflow=0,
            pool_recycle=300,
        )
    Base.metadata.create_all(engine)
    _migrate(engine)
    _engine = engine
    _factory = sessionmaker(bind=engine, expire_on_commit=False)
    prune_old_rows()


@contextmanager
def session_scope():
    init_db()
    session = _factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _user(row: User) -> UserRecord:
    return UserRecord(
        id=row.id,
        email=row.email,
        name=row.name or "",
        password_hash=row.password_hash,
        google_sub=row.google_sub,
        email_verified_at=row.email_verified_at,
    )


def _profile(row: Profile) -> ProfileRecord:
    return ProfileRecord(
        user_id=row.user_id,
        job_description=row.job_description or "",
        job_source=row.job_source or "",
        resume_text=row.resume_text or "",
        resume_source=row.resume_source or "",
        updated_at=row.updated_at,
        job_file_id=row.job_file_id or "",
        resume_file_id=row.resume_file_id or "",
    )


def _script_payload(raw: str) -> dict:
    try:
        loaded = json.loads(raw or "[]")
    except json.JSONDecodeError:
        loaded = []
    if isinstance(loaded, list):
        return {"questions": loaded, "bridges": {}}
    if isinstance(loaded, dict):
        loaded.setdefault("questions", [])
        if not isinstance(loaded.get("bridges"), dict):
            loaded["bridges"] = {}
        return loaded
    return {"questions": [], "bridges": {}}


def _interview(row: Interview) -> InterviewRecord:
    payload = _script_payload(row.questions_json)
    questions = tuple(str(item).strip() for item in payload.get("questions") or [] if str(item).strip())
    bridges: dict[int, str] = {}
    for key, value in (payload.get("bridges") or {}).items():
        try:
            bridges[int(key)] = str(value).strip()
        except (TypeError, ValueError):
            continue
    return InterviewRecord(
        id=row.id,
        user_id=row.user_id,
        job_description=row.job_description or "",
        resume_text=row.resume_text or "",
        questions=questions,
        current_index=row.current_index or 0,
        status=row.status,
        created_at=row.created_at,
        interviewer_name=str(payload.get("interviewer_name") or ""),
        interviewer_title=str(payload.get("interviewer_title") or ""),
        introduction=str(payload.get("introduction") or ""),
        bridges=bridges,
        role_name=str(payload.get("role_name") or ""),
        job_source=str(payload.get("job_source") or ""),
        resume_source=str(payload.get("resume_source") or ""),
        role_brief=str(payload.get("role_brief") or ""),
        brief_done=bool(payload.get("brief_done", not payload.get("role_brief"))),
        mic_checked=bool(payload.get("mic_checked", True)),
        chat_done=bool(payload.get("chat_done", True)),
        chat_wrap=bool(payload.get("chat_wrap", False)),
        chat_started_at=str(payload.get("chat_started_at") or ""),
        chat_log=tuple(
            (str(item.get("speaker") or ""), str(item.get("text") or ""))
            for item in (payload.get("chat") or [])
            if isinstance(item, dict)
        ),
        job_file_id=str(payload.get("job_file_id") or ""),
        resume_file_id=str(payload.get("resume_file_id") or ""),
    )


def _turn(row: Turn) -> TurnRecord:
    return TurnRecord(
        id=row.id,
        interview_id=row.interview_id,
        question_index=row.question_index,
        question_text=row.question_text or "",
        transcript=row.transcript or "",
        model_answer=row.model_answer or "",
        guidance=row.guidance or "",
        stop_reason=row.stop_reason or "",
    )


def create_password_user(name: str, email: str, password_hash: str) -> UserRecord:
    email = email.strip().lower()
    now = utcnow()
    try:
        with session_scope() as session:
            existing = session.scalar(select(User).where(User.email == email))
            if existing is not None:
                raise EmailTaken()
            row = User(
                id=str(uuid.uuid4()),
                email=email,
                name=name.strip()[:80],
                password_hash=password_hash,
                google_sub=None,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            return _user(row)
    except IntegrityError as exc:
        raise EmailTaken() from exc


def get_user(user_id: str) -> UserRecord | None:
    with session_scope() as session:
        row = session.get(User, user_id)
        return _user(row) if row else None


def get_user_by_email(email: str) -> UserRecord | None:
    with session_scope() as session:
        row = session.scalar(select(User).where(User.email == email.strip().lower()))
        return _user(row) if row else None


def upsert_google_user(email: str, name: str, google_sub: str) -> UserRecord:
    email = email.strip().lower()
    name = " ".join(name.split()).strip()[:80]
    now = utcnow()
    with session_scope() as session:
        by_sub = session.scalar(select(User).where(User.google_sub == google_sub))
        if by_sub is not None:
            if name and not by_sub.name:
                by_sub.name = name
            by_sub.updated_at = now
            if by_sub.email_verified_at is None:
                by_sub.email_verified_at = now
            return _user(by_sub)

        by_email = session.scalar(select(User).where(User.email == email))
        if by_email is not None:
            if by_email.google_sub and by_email.google_sub != google_sub:
                raise AuthLinkError(
                    "That email is already linked to a different Google account."
                )
            by_email.google_sub = google_sub
            if name:
                by_email.name = name
            by_email.updated_at = now
            if by_email.email_verified_at is None:
                by_email.email_verified_at = now
            return _user(by_email)

        row = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name or email.split("@", 1)[0][:80],
            password_hash=None,
            google_sub=google_sub,
            email_verified_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        return _user(row)


def get_profile(user_id: str) -> ProfileRecord | None:
    with session_scope() as session:
        row = session.get(Profile, user_id)
        return _profile(row) if row else None


def save_profile(
    user_id: str,
    job_description: str,
    job_source: str,
    resume_text: str,
    resume_source: str,
    job_file_id: str | None = None,
    resume_file_id: str | None = None,
) -> ProfileRecord:
    now = utcnow()
    with session_scope() as session:
        row = session.get(Profile, user_id)
        if row is None:
            row = Profile(
                user_id=user_id,
                job_description=job_description,
                job_source=job_source[:300],
                resume_text=resume_text,
                resume_source=resume_source[:300],
                job_file_id=(job_file_id or "")[:36],
                resume_file_id=(resume_file_id or "")[:36],
                updated_at=now,
            )
            session.add(row)
        else:
            row.job_description = job_description
            row.job_source = job_source[:300]
            row.resume_text = resume_text
            row.resume_source = resume_source[:300]
            if job_file_id is not None:
                row.job_file_id = job_file_id[:36]
            if resume_file_id is not None:
                row.resume_file_id = resume_file_id[:36]
            row.updated_at = now
        return _profile(row)


def create_interview(
    user_id: str,
    job_description: str,
    resume_text: str,
    questions: list[str],
    interviewer_name: str = "",
    interviewer_title: str = "",
    introduction: str = "",
    role_name: str = "",
    job_source: str = "",
    resume_source: str = "",
    role_brief: str = "",
    job_file_id: str = "",
    resume_file_id: str = "",
) -> InterviewRecord:
    ensure_interview_budget(user_id)
    now = utcnow()
    with session_scope() as session:
        active = session.scalars(
            select(Interview).where(
                Interview.user_id == user_id,
                Interview.status == "active",
            )
        ).all()
        for row in active:
            row.status = "replaced"
        interview = Interview(
            id=str(uuid.uuid4()),
            user_id=user_id,
            job_description=job_description,
            resume_text=resume_text,
            questions_json=json.dumps(
                {
                    "interviewer_name": interviewer_name,
                    "interviewer_title": interviewer_title,
                    "introduction": introduction,
                    "role_name": role_name,
                    "job_source": job_source,
                    "resume_source": resume_source,
                    "role_brief": role_brief,
                    "brief_done": False,
                    "mic_checked": False,
                    "chat_done": False,
                    "chat_wrap": False,
                    "chat_started_at": "",
                    "chat": [],
                    "questions": list(questions),
                    "bridges": {},
                    "job_file_id": job_file_id,
                    "resume_file_id": resume_file_id,
                }
            ),
            current_index=0,
            status="active",
            created_at=now,
        )
        session.add(interview)
        return _interview(interview)


def get_interview(interview_id: str) -> InterviewRecord | None:
    with session_scope() as session:
        try:
            row = _owned_interview(session, interview_id)
        except NotOwner:
            return None
        return _interview(row) if row else None


def list_interviews(user_id: str, limit: int = 100, offset: int = 0) -> list[InterviewRecord]:
    with session_scope() as session:
        rows = session.scalars(
            select(Interview)
            .where(Interview.user_id == user_id)
            .order_by(Interview.created_at.desc())
            .offset(max(0, offset))
            .limit(limit)
        ).all()
        return [_interview(row) for row in rows]


def newest_interview_with_materials(user_id: str) -> InterviewRecord | None:
    """Most recent interview that still has a job description or resume."""
    with session_scope() as session:
        row = session.scalar(
            select(Interview)
            .where(
                Interview.user_id == user_id,
                or_(
                    func.length(func.trim(Interview.job_description)) > 0,
                    func.length(func.trim(Interview.resume_text)) > 0,
                ),
            )
            .order_by(Interview.created_at.desc())
        )
        return _interview(row) if row else None


def count_interviews(user_id: str) -> int:
    with session_scope() as session:
        total = session.scalar(select(func.count()).select_from(Interview).where(Interview.user_id == user_id))
        return int(total or 0)


def latest_interview(user_id: str) -> InterviewRecord | None:
    with session_scope() as session:
        row = session.scalar(
            select(Interview)
            .where(
                Interview.user_id == user_id,
                Interview.status.in_(("active", "completed")),
            )
            .order_by(Interview.created_at.desc())
        )
        return _interview(row) if row else None


def set_current_index(interview_id: str, index: int) -> None:
    with _script_lock(interview_id):
        with session_scope() as session:
            row = _owned_interview(session, interview_id)
            if row is not None:
                row.current_index = max(0, index)


def _script_lock(interview_id: str) -> threading.Lock:
    with _script_locks_guard:
        if len(_script_locks) > 1000:
            _script_locks.clear()
        return _script_locks.setdefault(interview_id, threading.Lock())


def _owned_interview(session, interview_id: str) -> Interview | None:
    row = session.get(Interview, interview_id)
    actor = _actor.get()
    if row is None:
        return None
    if actor and row.user_id != actor:
        raise NotOwner()
    return row


def _update_script(interview_id: str, change) -> None:
    with _script_lock(interview_id):
        with session_scope() as session:
            row = _owned_interview(session, interview_id)
            if row is None:
                return
            if session.get_bind().dialect.name == "postgresql":
                row = session.scalar(select(Interview).where(Interview.id == interview_id).with_for_update())
                if row is None:
                    return
            payload = _script_payload(row.questions_json)
            change(payload)
            row.questions_json = json.dumps(payload)


def mark_mic_checked(interview_id: str) -> None:
    _update_script(interview_id, lambda payload: payload.__setitem__("mic_checked", True))


def start_small_talk(interview_id: str, opener: str) -> None:
    def change(payload: dict) -> None:
        if payload.get("chat"):
            return
        payload["chat"] = [{"speaker": "interviewer", "text": opener}]
        payload["chat_started_at"] = utcnow().isoformat()

    _update_script(interview_id, change)


def append_chat(interview_id: str, speaker: str, text: str, *, wrap: bool = False) -> None:
    spoken = " ".join((text or "").split())
    if not spoken:
        return

    def change(payload: dict) -> None:
        chat = payload.get("chat")
        if not isinstance(chat, list):
            chat = []
        chat.append({"speaker": speaker, "text": spoken[:800]})
        payload["chat"] = chat
        if wrap:
            payload["chat_wrap"] = True

    _update_script(interview_id, change)


def mark_chat_done(interview_id: str) -> None:
    _update_script(interview_id, lambda payload: payload.__setitem__("chat_done", True))


def mark_brief_done(interview_id: str) -> None:
    _update_script(interview_id, lambda payload: payload.__setitem__("brief_done", True))


def set_bridge(interview_id: str, question_index: int, bridge: str) -> None:
    text = " ".join((bridge or "").split())[:240]
    if not text:
        return

    def change(payload: dict) -> None:
        bridges = payload.get("bridges")
        if not isinstance(bridges, dict):
            bridges = {}
        bridges[str(question_index)] = text
        payload["bridges"] = bridges

    _update_script(interview_id, change)


def set_interview_status(interview_id: str, status: str) -> None:
    with session_scope() as session:
        row = _owned_interview(session, interview_id)
        if row is not None:
            row.status = status


def _turns_allowed(session, interview_id: str) -> bool:
    try:
        return _owned_interview(session, interview_id) is not None
    except NotOwner:
        return False


def get_turn(interview_id: str, question_index: int) -> TurnRecord | None:
    with session_scope() as session:
        if not _turns_allowed(session, interview_id):
            return None
        row = session.scalar(
            select(Turn).where(
                Turn.interview_id == interview_id,
                Turn.question_index == question_index,
            )
        )
        return _turn(row) if row else None


def list_turns(interview_id: str) -> list[TurnRecord]:
    with session_scope() as session:
        if not _turns_allowed(session, interview_id):
            return []
        rows = session.scalars(
            select(Turn)
            .where(Turn.interview_id == interview_id)
            .order_by(Turn.question_index)
        ).all()
        return [_turn(row) for row in rows]


def save_turn(
    interview_id: str,
    question_index: int,
    question_text: str,
    transcript: str,
    model_answer: str,
    guidance: str,
    stop_reason: str,
) -> TurnRecord:
    now = utcnow()
    with session_scope() as session:
        if _owned_interview(session, interview_id) is None:
            raise NotOwner()
        row = session.scalar(
            select(Turn).where(
                Turn.interview_id == interview_id,
                Turn.question_index == question_index,
            )
        )
        if row is None:
            row = Turn(
                id=str(uuid.uuid4()),
                interview_id=interview_id,
                question_index=question_index,
                question_text=question_text,
                transcript=transcript,
                model_answer=model_answer,
                guidance=guidance,
                stop_reason=stop_reason[:20],
                created_at=now,
            )
            session.add(row)
        else:
            row.question_text = question_text
            row.transcript = transcript
            row.model_answer = model_answer
            row.guidance = guidance
            row.stop_reason = stop_reason[:20]
        return _turn(row)


def delete_turn(interview_id: str, question_index: int) -> None:
    with session_scope() as session:
        if _owned_interview(session, interview_id) is None:
            return
        row = session.scalar(
            select(Turn).where(
                Turn.interview_id == interview_id,
                Turn.question_index == question_index,
            )
        )
        if row is not None:
            session.delete(row)


def set_actor(user_id: str | None) -> None:
    _actor.set(user_id)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _migrate(engine) -> None:
    dialect = engine.dialect.name
    timestamp = "TIMESTAMP" if dialect == "sqlite" else "TIMESTAMP WITH TIME ZONE"
    additions = {
        "users": [("email_verified_at", timestamp)],
        "profiles": [
            ("job_file_id", "VARCHAR(36) DEFAULT ''"),
            ("resume_file_id", "VARCHAR(36) DEFAULT ''"),
        ],
    }
    existing = inspect(engine)
    with engine.begin() as conn:
        for table, columns in additions.items():
            if not existing.has_table(table):
                continue
            present = {column["name"] for column in existing.get_columns(table)}
            for name, ddl in columns:
                if name in present:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def prune_old_rows() -> None:
    now = utcnow()
    with session_scope() as session:
        old_events = session.scalars(
            select(AppEvent).where(AppEvent.created_at < now - timedelta(days=EVENT_RETENTION_DAYS))
        ).all()
        for row in old_events:
            session.delete(row)
        replaced = session.scalars(
            select(Interview).where(
                Interview.status == "replaced",
                Interview.created_at < now - timedelta(days=REPLACED_INTERVIEW_DAYS),
            )
        ).all()
        for interview in replaced:
            turns = session.scalars(select(Turn).where(Turn.interview_id == interview.id)).all()
            for turn in turns:
                session.delete(turn)
            session.delete(interview)


def start_of_local_day() -> datetime:
    now = datetime.now(APP_TIMEZONE)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _daily_limits() -> tuple[int, int]:
    from interview_app import config

    return config.max_interviews_per_day(), config.max_model_calls_per_day()


def interviews_today(user_id: str) -> int:
    with session_scope() as session:
        total = session.scalar(
            select(func.count())
            .select_from(Interview)
            .where(Interview.user_id == user_id, Interview.created_at >= start_of_local_day())
        )
        return int(total or 0)


def model_calls_today(user_id: str) -> int:
    with session_scope() as session:
        total = session.scalar(
            select(func.count())
            .select_from(AppEvent)
            .where(
                AppEvent.user_id == user_id,
                AppEvent.kind == "model_call",
                AppEvent.created_at >= start_of_local_day(),
            )
        )
        return int(total or 0)


def usage_today(user_id: str) -> tuple[int, int, int, int]:
    interviews, calls = _daily_limits()
    return interviews_today(user_id), interviews, model_calls_today(user_id), calls


def ensure_interview_budget(user_id: str) -> None:
    used, limit, _calls, _call_limit = usage_today(user_id)
    if used >= limit:
        raise QuotaExceeded(
            f"This account has started {limit} interviews today. The allowance resets overnight."
        )


def charge_model_call(user_id: str) -> None:
    _interviews, _interview_limit, used, limit = usage_today(user_id)
    if used >= limit:
        raise QuotaExceeded(
            "This account has reached today's limit for interviewer replies. It resets overnight."
        )
    record_event(user_id, "model_call", "")


def record_event(user_id: str | None, kind: str, message: str) -> None:
    text_value = " ".join((message or "").split())[:300]
    try:
        with session_scope() as session:
            session.add(
                AppEvent(
                    id=str(uuid.uuid4()),
                    user_id=(user_id or "")[:36],
                    kind=kind[:40],
                    message=text_value,
                    created_at=utcnow(),
                )
            )
    except Exception:
        return


def save_contact_message(reply_email: str, message: str) -> None:
    text = (message or "").strip()
    if not text:
        return
    with session_scope() as session:
        session.add(
            ContactMessage(
                id=str(uuid.uuid4()),
                reply_email=(reply_email or "").strip()[:320],
                message=text[:4000],
                created_at=utcnow(),
            )
        )


def recent_contact_messages(limit: int = 20) -> list[tuple[datetime, str, str]]:
    with session_scope() as session:
        rows = session.scalars(
            select(ContactMessage).order_by(ContactMessage.created_at.desc()).limit(limit)
        ).all()
        return [(row.created_at, row.reply_email or "", row.message or "") for row in rows]


def recent_events(kind: str, limit: int = 30) -> list[tuple[datetime, str, str]]:
    with session_scope() as session:
        rows = session.scalars(
            select(AppEvent)
            .where(AppEvent.kind == kind)
            .order_by(AppEvent.created_at.desc())
            .limit(limit)
        ).all()
        return [(row.created_at, row.user_id, row.message) for row in rows]


def create_login_session(session_id: str, user_id: str, expires_at: datetime) -> None:
    now = utcnow()
    with session_scope() as session:
        session.add(
            LoginSession(
                id=session_id,
                user_id=user_id,
                expires_at=expires_at,
                revoked_at=None,
                created_at=now,
            )
        )


def login_session_active(session_id: str, user_id: str, now: datetime | None = None) -> bool:
    current = now or utcnow()
    with session_scope() as session:
        row = session.get(LoginSession, session_id)
        if row is None or row.user_id != user_id or row.revoked_at is not None:
            return False
        expires = _aware(row.expires_at)
        return expires is not None and expires > current


def revoke_login_session(session_id: str) -> None:
    with session_scope() as session:
        row = session.get(LoginSession, session_id)
        if row is not None and row.revoked_at is None:
            row.revoked_at = utcnow()


def revoke_user_sessions(user_id: str) -> None:
    now = utcnow()
    with session_scope() as session:
        rows = session.scalars(select(LoginSession).where(LoginSession.user_id == user_id)).all()
        for row in rows:
            if row.revoked_at is None:
                row.revoked_at = now


def login_locked(email: str, now: datetime | None = None) -> bool:
    current = now or utcnow()
    with session_scope() as session:
        row = session.get(LoginGuard, email.strip().lower())
        locked = _aware(row.locked_until) if row is not None else None
        return bool(locked and locked > current)


def note_login_failure(email: str, *, limit: int = 8, lock_seconds: int = 15 * 60) -> None:
    email = email.strip().lower()
    now = utcnow()
    with session_scope() as session:
        row = session.get(LoginGuard, email)
        if row is None:
            row = LoginGuard(email=email, failures=1, locked_until=None, updated_at=now)
            session.add(row)
        else:
            row.failures = int(row.failures or 0) + 1
            row.updated_at = now
        if row.failures >= limit:
            row.locked_until = now + timedelta(seconds=lock_seconds)


def clear_login_failures(email: str) -> None:
    with session_scope() as session:
        row = session.get(LoginGuard, email.strip().lower())
        if row is not None:
            session.delete(row)


def referenced_file_ids(session, user_id: str) -> set[str]:
    kept: set[str] = set()
    profile = session.get(Profile, user_id)
    if profile is not None:
        kept.add(profile.job_file_id or "")
        kept.add(profile.resume_file_id or "")
    interviews = session.scalars(select(Interview).where(Interview.user_id == user_id)).all()
    for interview in interviews:
        payload = _script_payload(interview.questions_json)
        kept.add(str(payload.get("job_file_id") or ""))
        kept.add(str(payload.get("resume_file_id") or ""))
    kept.discard("")
    return kept


def store_file(user_id: str, kind: str, filename: str, data: bytes, content_type: str = "") -> str | None:
    if not data or len(data) > 10 * 1024 * 1024:
        return None
    with session_scope() as session:
        total = int(
            session.scalar(
                select(func.coalesce(func.sum(StoredFile.size), 0)).where(StoredFile.user_id == user_id)
            )
            or 0
        )
        if total + len(data) > STORAGE_CAP_BYTES:
            kept = referenced_file_ids(session, user_id)
            oldest = session.scalars(
                select(StoredFile).where(StoredFile.user_id == user_id).order_by(StoredFile.created_at)
            ).all()
            for row in oldest:
                if row.id in kept:
                    continue
                total -= int(row.size or 0)
                session.delete(row)
                if total + len(data) <= STORAGE_CAP_BYTES:
                    break
            if total + len(data) > STORAGE_CAP_BYTES:
                return None
        file_id = str(uuid.uuid4())
        session.add(
            StoredFile(
                id=file_id,
                user_id=user_id,
                kind=kind[:20],
                filename=(filename or "upload")[:300],
                content_type=(content_type or "")[:120],
                size=len(data),
                data=data,
                created_at=utcnow(),
            )
        )
        return file_id


def newest_stored_file(user_id: str, kind: str) -> StoredFileInfo | None:
    with session_scope() as session:
        row = session.scalar(
            select(StoredFile)
            .where(StoredFile.user_id == user_id, StoredFile.kind == kind)
            .order_by(StoredFile.created_at.desc())
        )
        if row is None:
            return None
        return StoredFileInfo(
            id=row.id,
            kind=row.kind or "",
            filename=row.filename or "",
            created_at=row.created_at,
        )


def read_file(file_id: str, user_id: str) -> tuple[str, bytes] | None:
    if not file_id:
        return None
    with session_scope() as session:
        row = session.get(StoredFile, file_id)
        if row is None or row.user_id != user_id:
            return None
        return row.filename or "upload", bytes(row.data or b"")


def save_password_token(user_id: str, token_hash: str, purpose: str, expires_at: datetime) -> None:
    with session_scope() as session:
        session.add(
            PasswordReset(
                id=str(uuid.uuid4()),
                user_id=user_id,
                token_hash=token_hash,
                purpose=purpose[:20],
                expires_at=expires_at,
                used_at=None,
                created_at=utcnow(),
            )
        )


def take_password_token(token_hash: str, purpose: str) -> str | None:
    now = utcnow()
    with session_scope() as session:
        row = session.scalar(select(PasswordReset).where(PasswordReset.token_hash == token_hash))
        if row is None or row.purpose != purpose or row.used_at is not None:
            return None
        expires = _aware(row.expires_at)
        if expires is None or expires < now:
            return None
        row.used_at = now
        return row.user_id


def mark_email_verified(user_id: str) -> None:
    with session_scope() as session:
        row = session.get(User, user_id)
        if row is not None and row.email_verified_at is None:
            row.email_verified_at = utcnow()


def set_password_hash(user_id: str, password_hash: str) -> None:
    with session_scope() as session:
        row = session.get(User, user_id)
        if row is None:
            return
        row.password_hash = password_hash
        row.updated_at = utcnow()


def export_account(user_id: str) -> dict:
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            return {}
        profile = session.get(Profile, user_id)
        files = session.scalars(select(StoredFile).where(StoredFile.user_id == user_id)).all()
        interviews = session.scalars(
            select(Interview).where(Interview.user_id == user_id).order_by(Interview.created_at)
        ).all()
        payload = {
            "account": {
                "email": user.email,
                "name": user.name,
                "created_at": user.created_at.isoformat() if user.created_at else "",
            },
            "profile": {
                "job_description": profile.job_description if profile else "",
                "job_source": profile.job_source if profile else "",
                "resume_text": profile.resume_text if profile else "",
                "resume_source": profile.resume_source if profile else "",
            },
            "files": [
                {"id": item.id, "kind": item.kind, "filename": item.filename, "size": item.size}
                for item in files
            ],
            "interviews": [],
        }
        for interview in interviews:
            turns = session.scalars(
                select(Turn).where(Turn.interview_id == interview.id).order_by(Turn.question_index)
            ).all()
            payload["interviews"].append(
                {
                    "id": interview.id,
                    "status": interview.status,
                    "created_at": interview.created_at.isoformat() if interview.created_at else "",
                    "job_description": interview.job_description,
                    "resume_text": interview.resume_text,
                    "script": _script_payload(interview.questions_json),
                    "turns": [
                        {
                            "question": turn.question_text,
                            "transcript": turn.transcript,
                            "model_answer": turn.model_answer,
                            "guidance": turn.guidance,
                        }
                        for turn in turns
                    ],
                }
            )
        return payload


def delete_account(user_id: str) -> None:
    with session_scope() as session:
        interview_ids = list(
            session.scalars(select(Interview.id).where(Interview.user_id == user_id)).all()
        )
        if interview_ids:
            turns = session.scalars(select(Turn).where(Turn.interview_id.in_(interview_ids))).all()
            for turn in turns:
                session.delete(turn)
            interviews = session.scalars(select(Interview).where(Interview.user_id == user_id)).all()
            for interview in interviews:
                session.delete(interview)
        for model, column in (
            (StoredFile, StoredFile.user_id),
            (AppEvent, AppEvent.user_id),
            (LoginSession, LoginSession.user_id),
            (PasswordReset, PasswordReset.user_id),
        ):
            rows = session.scalars(select(model).where(column == user_id)).all()
            for row in rows:
                session.delete(row)
        profile = session.get(Profile, user_id)
        if profile is not None:
            session.delete(profile)
        user = session.get(User, user_id)
        if user is not None:
            guard = session.get(LoginGuard, user.email)
            if guard is not None:
                session.delete(guard)
            session.delete(user)
