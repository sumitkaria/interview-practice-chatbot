"""Grok requests for questions, coaching, and image text."""

from __future__ import annotations

import base64
import json
import threading

import httpx
from openai import APIConnectionError, APIStatusError, AuthenticationError, OpenAI, RateLimitError

from interview_app import config, db, prompts

_MODEL_SLOTS = threading.BoundedSemaphore(2)

class GrokError(Exception):
    """A Grok request could not be completed."""


class GrokNotConfigured(GrokError):
    """No xAI API key is available."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or (
                "Add XAI_API_KEY to Streamlit secrets or a local .env file. "
                "Create a key at https://console.x.ai/ and add credits to that account."
            )
        )


def require_api_key() -> str:
    key = config.xai_api_key()
    if not key:
        raise GrokNotConfigured()
    return key


def build_client(api_key: str | None = None) -> OpenAI:
    return OpenAI(
        api_key=api_key or require_api_key(),
        base_url=config.XAI_BASE_URL,
        timeout=httpx.Timeout(180.0),
    )


def _sanitize(exc: Exception, api_key: str) -> str:
    text = " ".join(str(exc).split())
    if api_key:
        text = text.replace(api_key, "XAI_API_KEY")
    return text[:240]


def response_text(response) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) not in {None, "message"}:
            continue
        for part in getattr(item, "content", None) or []:
            value = getattr(part, "text", None)
            if value:
                chunks.append(value)
    if chunks:
        return "\n".join(chunks)
    raise GrokError("Grok returned an empty response. Try again.")


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
        raise GrokError("The interviewer is with someone else right now. Wait a moment and try again.")
    grok = client or build_client(api_key)
    try:
        if user_id:
            try:
                db.charge_model_call(user_id)
            except db.QuotaExceeded as exc:
                raise GrokError(str(exc)) from exc
        response = grok.responses.create(
            model=config.grok_model(),
            reasoning={"effort": config.grok_effort()},
            store=False,
            max_output_tokens=max_output_tokens,
            prompt_cache_key=cache_key,
            input=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_content},
            ],
        )
    except AuthenticationError as exc:
        _remember_model_error(user_id, "The Grok API key was rejected.")
        raise GrokError(
            "The Grok API key was rejected. Check XAI_API_KEY in Streamlit secrets."
        ) from exc
    except RateLimitError as exc:
        _remember_model_error(user_id, "Grok is rate limited or out of credits.")
        raise GrokError(
            "Grok is rate limited, or the account needs more credits. "
            "Check the balance at https://console.x.ai/."
        ) from exc
    except APIStatusError as exc:
        _remember_model_error(user_id, f"Grok returned {exc.status_code}.")
        if exc.status_code in {402, 403}:
            raise GrokError(
                "Grok refused the request. Check that the API key is valid and the account has credits."
            ) from exc
        raise GrokError(f"Grok returned an error ({exc.status_code}). {_sanitize(exc, api_key)}") from exc
    except APIConnectionError as exc:
        _remember_model_error(user_id, "Could not reach the Grok API.")
        raise GrokError("Could not reach the Grok API. Check the network and try again.") from exc
    except GrokError:
        raise
    except Exception as exc:
        _remember_model_error(user_id, _sanitize(exc, api_key))
        raise GrokError(f"Grok could not complete that request. {_sanitize(exc, api_key)}") from exc
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
        raise GrokError("Grok did not return interview questions. Try again.") from exc


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
            raise GrokError("Grok returned an empty answer. Try again.")
        return cleaned, "That already has a clear point. Next time, add the result in one sentence.", ""


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
            raise GrokError("Grok returned an empty answer. Try again.")
        return reply
    reply = ""
    if isinstance(payload, dict):
        reply = str(payload.get("reply") or payload.get("answer") or "").strip()
    if not reply:
        raise GrokError("Grok returned an empty answer. Try again.")
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
            "type": "input_image",
            "image_url": f"data:{mime};base64,{encoded}",
            "detail": "high",
        },
        {"type": "input_text", "text": prompts.IMAGE_INSTRUCTIONS},
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
        raise GrokError("Grok could not read that image. Paste the text instead.")
    return cleaned
