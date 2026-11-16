"""Browser components for the session cookie and spoken answers."""

from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_ROOT = Path(__file__).resolve().parent / "frontend"
_voice = None
_session = None


def interview_voice(question: str, question_token: str, max_seconds: int = 180):
    global _voice
    if _voice is None:
        _voice = components.declare_component("interview_voice", path=str(_ROOT / "voice"))
    return _voice(
        question=question,
        questionToken=question_token,
        maxSeconds=max_seconds,
        key=f"voice-{question_token}",
        default=None,
    )


def session_bridge(action: str, token: str = "", max_age: int = 0, nonce: str = ""):
    global _session
    if _session is None:
        _session = components.declare_component(
            "interview_session",
            path=str(_ROOT / "session"),
        )
    return _session(
        action=action,
        token=token,
        maxAge=max_age,
        nonce=nonce,
        key="interview-session",
        default=None,
    )
