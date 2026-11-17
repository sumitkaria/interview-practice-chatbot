"""Claude requests for questions, coaching, and image text."""

from __future__ import annotations

import base64
import json
import threading

from anthropic import APIConnectionError, APIStatusError, Anthropic, AuthenticationError, RateLimitError

from interview_app import config, db, prompts

_MODEL_SLOTS = threading.BoundedSemaphore(2)


class ClaudeError(Exception):
    """A Claude request could not be completed."""


class ClaudeNotConfigured(ClaudeError):
    """No AI key is available."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "The AI interviewer is not available right now."
        )


def require_api_key() -> str:
    key = config.anthropic_api_key()
    if not key:
        raise ClaudeNotConfigured()
    return key


def build_client(api_key: str | None = None) -> Anthropic:
    return Anthropic(
        api_key=api_key or require_api_key(),
        timeout=180.0,
    )


def _sanitize(exc: Exception, api_key: str) -> str:
    text = " ".join(str(exc).split())
    if api_key:
        text = text.replace(api_key, "the AI key")
    return text[:240]


def response_text(response) -> str:
    chunks: list[str] = []
    for block in getattr(response, "content", None) or []:
        if isinstance(block, dict):
            if block.get("type") not in {None, "text"}:
                continue
            value = block.get("text")
        else:
            if getattr(block, "type", None) not in {None, "text"}:
                continue
            value = getattr(block, "text", None)
        if value:
            chunks.append(value)
    if chunks:
        return "\n".join(chunks)
    raise ClaudeError("The AI interviewer returned an empty response. Try again.")


def complete(
    instructions: str,
    user_content,
    *,
    cache_key: str,
    max_output_tokens: int,
    client=None,
    user_id: str | None = None,
) -> str:
    api_key = require_api_key()
    if not _MODEL_SLOTS.acquire(timeout=8):
        raise ClaudeError("The interviewer is with someone else right now. Wait a moment and try again.")
    claude = client or build_client(api_key)
    try:
        if user_id:
            try:
                db.charge_model_call(user_id)
            except db.QuotaExceeded as exc:
                raise ClaudeError(str(exc)) from exc
        model, effort = db.model_settings(user_id) if user_id else (config.claude_model(), config.claude_effort())
        response = claude.messages.create(
            model=model,
            max_tokens=max_output_tokens,
            system=[
                {
                    "type": "text",
                    "text": instructions,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
            output_config={"effort": effort},
            metadata={"user_id": cache_key[:256]},
        )
    except AuthenticationError as exc:
        _remember_model_error(user_id, "The AI key was rejected.")
        raise ClaudeError("The AI interviewer could not sign in. Try again in a moment.") from exc
    except RateLimitError as exc:
        _remember_model_error(user_id, "The AI interviewer is rate limited or out of credits.")
        raise ClaudeError("The AI interviewer is busy right now. Try again in a moment.") from exc
    except APIStatusError as exc:
        _remember_model_error(user_id, f"The AI interviewer returned {exc.status_code}.")
        if exc.status_code in {402, 403}:
            raise ClaudeError("The AI interviewer could not answer. Try again in a moment.") from exc
        raise ClaudeError(f"The AI interviewer returned an error ({exc.status_code}). {_sanitize(exc, api_key)}") from exc
    except APIConnectionError as exc:
        _remember_model_error(user_id, "Could not reach the AI interviewer.")
        raise ClaudeError("Could not reach the AI interviewer. Try again.") from exc
    except ClaudeError:
        raise
    except Exception as exc:
        _remember_model_error(user_id, _sanitize(exc, api_key))
        raise ClaudeError(f"The AI interviewer could not complete that request. {_sanitize(exc, api_key)}") from exc
    finally:
        _MODEL_SLOTS.release()
    return response_text(response)


def _remember_model_error(user_id: str | None, message: str) -> None:
    db.record_event(user_id, "error", message)


def generate_questions(
    job_description: str,
    resume_text: str,
    *,
    cache_key: str,
    client=None,
    user_id: str | None = None,
) -> prompts.InterviewScript:
    interviewer_name = prompts.choose_interviewer_name()
    raw = complete(
        prompts.QUESTION_INSTRUCTIONS,
        prompts.questions_input(job_description, resume_text, interviewer_name),
        cache_key=cache_key,
        max_output_tokens=8000,
        client=client,
        user_id=user_id,
    )
    try:
        return prompts.normalize_interview(prompts.parse_model_json(raw), interviewer_name)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ClaudeError("The AI interviewer did not return questions. Try again.") from exc


def coach_answer(
    *,
    job_description: str,
    resume_text: str,
    question: str,
    transcript: str,
    prior: list[tuple[str, str]] | None = None,
    cache_key: str,
    client=None,
    user_id: str | None = None,
) -> tuple[str, str, str]:
    raw = complete(
        prompts.COACH_INSTRUCTIONS,
        prompts.coach_input(job_description, resume_text, question, transcript, prior),
        cache_key=cache_key,
        max_output_tokens=4000,
        client=client,
        user_id=user_id,
    )
    try:
        payload = prompts.parse_model_json(raw)
        return prompts.coach_from_payload(payload, raw, transcript)
    except (ValueError, TypeError, json.JSONDecodeError):
        cleaned = raw.strip()
        if not cleaned:
            raise ClaudeError("The AI interviewer returned an empty answer. Try again.")
        if not cleaned.startswith("{") and not cleaned.startswith("```"):
            cleaned = prompts.polish_spoken_answer(cleaned)
        return cleaned, "That already has a clear point. Next time, add the result in one sentence and tie it to this role.", ""


def continue_small_talk(
    *,
    history: list[tuple[str, str]],
    cache_key: str,
    client=None,
    user_id: str | None = None,
) -> str:
    lines = []
    for speaker, text in history[-4:]:
        who = "Interviewer" if speaker == "interviewer" else "Candidate"
        lines.append(f"{who}: {text}")
    raw = complete(
        prompts.SMALL_TALK_INSTRUCTIONS,
        "CONVERSATION SO FAR:\n" + ("\n".join(lines) or "None.") + "\n",
        cache_key=cache_key,
        max_output_tokens=200,
        client=client,
        user_id=user_id,
    )
    try:
        payload = prompts.parse_model_json(raw)
    except (ValueError, TypeError, json.JSONDecodeError):
        return "Glad to hear it."
    reply = str(payload.get("reply") or "").strip() if isinstance(payload, dict) else ""
    return reply or "Glad to hear it."


def answer_candidate_question(
    *,
    job_description: str,
    resume_text: str,
    question: str,
    interviewer_name: str,
    interviewer_title: str,
    cache_key: str,
    client=None,
    user_id: str | None = None,
) -> str:
    raw = complete(
        prompts.INTERVIEWER_REPLY_INSTRUCTIONS,
        (
            f"INTERVIEWER:\n{interviewer_name}, {interviewer_title}\n\n"
            f"JOB DESCRIPTION:\n{job_description.strip()}\n\n"
            f"CANDIDATE BACKGROUND:\n{resume_text.strip()}\n\n"
            f"CANDIDATE'S QUESTION:\n{question.strip()}\n"
        ),
        cache_key=cache_key,
        max_output_tokens=2000,
        client=client,
        user_id=user_id,
    )
    try:
        payload = prompts.parse_model_json(raw)
    except (ValueError, TypeError, json.JSONDecodeError):
        reply = raw.strip()
        if not reply:
            raise ClaudeError("The AI interviewer returned an empty answer. Try again.")
        return reply
    reply = ""
    if isinstance(payload, dict):
        reply = str(payload.get("reply") or payload.get("answer") or "").strip()
    if not reply:
        raise ClaudeError("The AI interviewer returned an empty answer. Try again.")
    return reply


def extract_document_text(
    data: bytes,
    mime: str,
    *,
    cache_key: str,
    client=None,
    user_id: str | None = None,
) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": encoded,
            },
        },
        {"type": "text", "text": prompts.IMAGE_INSTRUCTIONS},
    ]
    text = complete(
        "You extract text from document images.",
        content,
        cache_key=cache_key,
        max_output_tokens=4000,
        client=client,
        user_id=user_id,
    )
    cleaned = text.strip()
    if not cleaned:
        raise ClaudeError("The AI interviewer could not read that image. Paste the text instead.")
    return cleaned
