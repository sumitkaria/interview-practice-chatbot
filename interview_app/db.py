"""Per-user accounts, saved materials, and interview sessions."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

_engine = None
_factory = None


class EmailTaken(Exception):
    """An account with this email already exists."""


class AuthLinkError(Exception):
    """A Google account could not be linked to the email."""


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    job_description: Mapped[str] = mapped_column(Text, default="")
    job_source: Mapped[str] = mapped_column(String(300), default="")
    resume_text: Mapped[str] = mapped_column(Text, default="")
    resume_source: Mapped[str] = mapped_column(String(300), default="")
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


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str
    name: str
    password_hash: str | None
    google_sub: str | None


@dataclass(frozen=True)
class ProfileRecord:
    user_id: str
    job_description: str
    job_source: str
    resume_text: str
    resume_source: str
    updated_at: datetime


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
        engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    _engine = engine
    _factory = sessionmaker(bind=engine, expire_on_commit=False)


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
    )


def _profile(row: Profile) -> ProfileRecord:
    return ProfileRecord(
        user_id=row.user_id,
        job_description=row.job_description or "",
        job_source=row.job_source or "",
        resume_text=row.resume_text or "",
        resume_source=row.resume_source or "",
        updated_at=row.updated_at,
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
            return _user(by_email)

        row = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name or email.split("@", 1)[0][:80],
            password_hash=None,
            google_sub=google_sub,
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
                updated_at=now,
            )
            session.add(row)
        else:
            row.job_description = job_description
            row.job_source = job_source[:300]
            row.resume_text = resume_text
            row.resume_source = resume_source[:300]
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
) -> InterviewRecord:
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
                    "questions": list(questions),
                    "bridges": {},
                }
            ),
            current_index=0,
            status="active",
            created_at=now,
        )
        session.add(interview)
        return _interview(interview)


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
    with session_scope() as session:
        row = session.get(Interview, interview_id)
        if row is not None:
            row.current_index = max(0, index)


def set_bridge(interview_id: str, question_index: int, bridge: str) -> None:
    text = " ".join((bridge or "").split())[:240]
    if not text:
        return
    with session_scope() as session:
        row = session.get(Interview, interview_id)
        if row is None:
            return
        payload = _script_payload(row.questions_json)
        payload["bridges"][str(question_index)] = text
        row.questions_json = json.dumps(payload)


def set_interview_status(interview_id: str, status: str) -> None:
    with session_scope() as session:
        row = session.get(Interview, interview_id)
        if row is not None:
            row.status = status


def get_turn(interview_id: str, question_index: int) -> TurnRecord | None:
    with session_scope() as session:
        row = session.scalar(
            select(Turn).where(
                Turn.interview_id == interview_id,
                Turn.question_index == question_index,
            )
        )
        return _turn(row) if row else None


def list_turns(interview_id: str) -> list[TurnRecord]:
    with session_scope() as session:
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
        row = session.scalar(
            select(Turn).where(
                Turn.interview_id == interview_id,
                Turn.question_index == question_index,
            )
        )
        if row is not None:
            session.delete(row)
