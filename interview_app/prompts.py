"""Instructions and parsers for interview questions and coaching."""

from __future__ import annotations

import json
import re
from typing import Any

QUESTION_INSTRUCTIONS = """
You prepare a spoken mock interview.

Return only a JSON object: {"questions": ["...", "..."]}
No markdown fences.

Write 6 questions.
Each question is at most 35 words and asks one thing.
The first question must be "Tell me about yourself."
Make the other questions specific to this job description and this candidate's background.
Mix role-specific questions with behavioral questions a hiring manager would actually ask.
Do not include answers, numbering, or commentary.
""".strip()

COACH_INSTRUCTIONS = """
You coach a candidate right after they answer an interview question out loud.

Return only a JSON object with two string keys, "answer" and "guidance".
No markdown fences.

answer:
- First person, as the candidate would say it.
- Natural spoken language, 70 to 120 words.
- No headings, bullets, brackets, labels, or placeholders.
- Use the candidate background and what they just said. Do not invent employers, titles, dates, metrics, or achievements.
- If the transcript conveys an answer, keep their meaning, examples, and claims, and make the wording clearer.
- If the transcript is missing, off topic, or too thin to convey an answer, write a strong answer from the background and the job.

guidance:
- Second person, 40 to 90 words.
- If they conveyed an answer, say what to keep and one concrete improvement.
- If they did not convey an answer, say that plainly and explain how to handle this kind of question.
""".strip()

IMAGE_INSTRUCTIONS = (
    "Extract every readable word from this page. Keep headings and lists as plain lines. "
    "Return the document text only, with no commentary."
)


def is_thin_transcript(transcript: str) -> bool:
    words = re.findall(r"[A-Za-z0-9']+", transcript or "")
    return len(words) < 5


def parse_model_json(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))


def normalize_questions(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        items = payload.get("questions", [])
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("The model did not return questions.")
    cleaned: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("question") or item.get("text") or "")
        else:
            text = str(item)
        text = re.sub(r"^\s*\d+[\).\:-]\s*", "", text).strip()
        if text:
            cleaned.append(text)
    if not cleaned:
        raise ValueError("The model did not return questions.")
    if "about yourself" not in cleaned[0].lower():
        cleaned.insert(0, "Tell me about yourself.")
    unique: list[str] = []
    seen: set[str] = set()
    for question in cleaned:
        key = question.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(question[:500])
        if len(unique) == 6:
            break
    return unique


def questions_input(job_description: str, resume_text: str) -> str:
    return (
        f"JOB DESCRIPTION:\n{job_description.strip()}\n\n"
        f"CANDIDATE BACKGROUND:\n{resume_text.strip()}\n"
    )


def coach_input(
    job_description: str,
    resume_text: str,
    question: str,
    transcript: str,
    prior: list[tuple[str, str]] | None = None,
) -> str:
    spoken = (transcript or "").strip()
    thin = is_thin_transcript(spoken)
    if thin:
        check = (
            "The transcript is empty or too thin to convey an answer. "
            "Write a full answer from the background and explain how to handle the question."
        )
    else:
        check = "The transcript conveys an answer. Stay close to what the candidate meant."
    history = _format_prior(prior or [])
    return (
        f"JOB DESCRIPTION:\n{job_description.strip()}\n\n"
        f"CANDIDATE BACKGROUND:\n{resume_text.strip()}\n\n"
        f"INTERVIEW QUESTION:\n{question.strip()}\n\n"
        f"WHAT THE CANDIDATE SAID OUT LOUD:\n{spoken or '[nothing captured]'}\n\n"
        f"TRANSCRIPT CHECK:\n{check}\n\n"
        f"EARLIER ANSWERS IN THIS SESSION:\n{history}\n"
    )


def _format_prior(prior: list[tuple[str, str]]) -> str:
    if not prior:
        return "None."
    blocks = []
    for question, transcript in prior[-5:]:
        spoken = (transcript or "").strip()[:400] or "[nothing captured]"
        blocks.append(f"Question: {question.strip()}\nSaid: {spoken}")
    return "\n\n".join(blocks)


def coach_from_payload(payload: Any, raw_text: str) -> tuple[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("The model did not return an answer.")
    answer = str(payload.get("answer") or "").strip()
    guidance = str(payload.get("guidance") or "").strip()
    if not answer:
        answer = raw_text.strip()
    if not answer:
        raise ValueError("The model returned an empty answer.")
    if not guidance:
        guidance = "Use the answer above as a starting point, then say it in your own words."
    return answer, guidance
