"""Instructions and parsers for interview questions and coaching."""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from typing import Any

INTERVIEWER_NAMES = (
    "Amelia Ward",
    "Priya Shah",
    "Elena Vasquez",
    "Hannah Okonkwo",
    "Claire Nguyen",
    "Sofia Rahman",
    "Maya Ellison",
    "Naomi Brooks",
    "Leila Haddad",
    "Grace Nakamura",
)

QUESTION_INSTRUCTIONS = """
You prepare a spoken mock interview led by a woman. She is a real interviewer, not a form.

Use the interviewer name given in the candidate packet. Do not change it.
Choose the title she would actually hold for this hire: a senior manager of this function at this organization. If the company is named, include it. If it is not, name the function only. Examples of the shape, not the words to copy: "Director of Analytics, Northwind" or "Engineering Manager, Payments".

Return only a JSON object with the keys "role", "title", "introduction", and "questions".
No markdown fences.

role:
The name of this interview, taken from the job description. Use the job title and the organization when it is named, such as "CFO, Capital Markets at ATB". Do not include the word "interview".

introduction:
Two or three sentences she says before any question. She gives her name and title, welcomes the candidate, and sets an easy tone. No question in the introduction.

questions:
Seven short spoken questions. Each asks one thing and stays under 30 words.
Write them in this order:
1. An easy opening question of the kind interviewers ask first, in the spirit of "Tell me about yourself."
2. Another easy, usual opening question, such as why this role or what drew them here. Keep it general.
3. A question they can answer well from their own experience, so they sound capable and settle in.
4 and 5. Read the job description, then infer what similar roles in this organization are actually accountable for. Ask about the skill that matters most, not a checklist. If a concrete skill is required, such as SQL, question 4 asks them to rate that skill from 1 to 10, and question 5 is a simple practical check they can answer out loud, such as a straightforward query. Do this for one important skill only.
6. One kinder question that touches a likely gap between their experience and the role. Do not embarrass them.
7. A closing question that lets them finish feeling capable, such as how they would spend the first month.

Sound like a person across a table. No numbering, no "as a hiring manager", and do not mention the résumé or the job description as documents.
""".strip()

COACH_INSTRUCTIONS = """
You write the answer a strong candidate would say out loud, then a note that builds confidence and repairs one weakness.

Interviewers listen for three things, in this order:
- The point, in the first sentence.
- One real example: the situation, what the candidate personally did, and the result.
- One line on why that matters for this role.

The answer should sound spoken. Use contractions. No headings, bullets, labels, brackets, or filler such as "leverage", "passionate", or "synergy".
For a rating from 1 to 10, keep the number they chose and add one piece of proof. Do not raise their score.
For a technical check such as SQL, give a simple correct answer they could say aloud.
Use only facts from their background and from what they just said. Do not invent employers, titles, dates, metrics, or tools.

Return only a JSON object with the string keys "answer", "guidance", and "bridge".
No markdown fences.

answer:
First person, 80 to 130 words.
If their words already contain an answer, keep their meaning, examples, and claims, and shape them into what an interviewer hopes to hear.
If the recording is empty, off topic, or too thin to be an answer, write a full genuine answer from the background.

guidance:
Second person, 40 to 80 words.
Begin with what already sounded credible. Then name one weakness and how to say it better next time.
If they did not really answer, say that kindly and explain how to handle this kind of question.

bridge:
One spoken sentence the interviewer will say before her next question.
React only to what they actually said. If they said almost nothing, do not pretend the answer was strong. Keep it light.
Do not ask the next question inside the bridge.
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


@dataclass(frozen=True)
class InterviewScript:
    interviewer_name: str
    interviewer_title: str
    introduction: str
    questions: tuple[str, ...]
    role_name: str = ""


def _clean_role_name(value: str) -> str:
    name = re.sub(r"\s+", " ", value).strip(" -–:.")
    name = re.sub(r"\binterview\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip(" -–:,")
    return name[:90]


def interview_name(job_description: str) -> str:
    """A short name for the practice session, taken from the job description."""
    text = (job_description or "").strip()
    if not text:
        return "Practice"
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" \t-•*")
        if line:
            lines.append(line)
    title = ""
    company = ""
    labeled_title = re.compile(
        r"^(?:job title|position title|position|role|title)\s*[:\-–]\s*(.+)$",
        re.IGNORECASE,
    )
    labeled_company = re.compile(
        r"^(?:company|organization|organisation|employer)\s*[:\-–]\s*(.+)$",
        re.IGNORECASE,
    )
    for line in lines[:40]:
        match = labeled_title.match(line)
        if match and not title:
            title = match.group(1).strip()
            continue
        match = labeled_company.match(line)
        if match and not company:
            company = match.group(1).strip()
    if not title:
        for line in lines[:10]:
            if re.match(
                r"^(about|overview|the role|job description|responsibilities|requirements|qualifications)\b",
                line,
                re.IGNORECASE,
            ):
                continue
            if len(line) > 70 or len(line.split()) > 14 or line.endswith("."):
                continue
            title = line
            break
    if title and not company:
        for index, line in enumerate(lines[:12]):
            if line == title or line.endswith(title):
                if index + 1 < len(lines):
                    nxt = lines[index + 1]
                    if 1 <= len(nxt.split()) <= 6 and not nxt.endswith("."):
                        if not re.match(r"^(about|reports|location|department)\b", nxt, re.IGNORECASE):
                            company = nxt
                break
    if not title:
        seeking = re.search(r"\b(?:seeking|hiring)\s+(?:an?\s+)?([A-Za-z][^.\n]{2,60})", text, re.IGNORECASE)
        if seeking:
            title = re.split(r"\s+(?:to|who|with|for)\b", seeking.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
    title = _clean_role_name(title)
    company = _clean_role_name(company)
    if company.lower().startswith("at "):
        company = company[3:].strip()
    if title and company and company.lower() not in title.lower():
        title = f"{title} at {company}"
    return title[:90] or "Practice"


def choose_interviewer_name() -> str:
    return random.choice(INTERVIEWER_NAMES)


def _is_opener(question: str) -> bool:
    lowered = question.lower()
    return "about yourself" in lowered or "about you" in lowered


def normalize_interview(payload: Any, interviewer_name: str) -> InterviewScript:
    if isinstance(payload, list):
        payload = {"questions": payload}
    if not isinstance(payload, dict):
        raise ValueError("The model did not return questions.")
    name = interviewer_name.strip() or choose_interviewer_name()
    role_name = _clean_role_name(str(payload.get("role") or payload.get("role_name") or ""))
    title = re.sub(r"\s+", " ", str(payload.get("title") or payload.get("interviewer_title") or "")).strip()
    title = (title or "Hiring Manager")[:120]
    introduction = re.sub(r"\s+", " ", str(payload.get("introduction") or "")).strip()
    if name.lower() not in introduction.lower():
        introduction = f"Hi, I'm {name}, {title}. Thanks for making the time. We'll keep this conversational."
    items = payload.get("questions", [])
    cleaned: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("question") or item.get("text") or "")
        else:
            text = str(item)
        text = re.sub(r"^\s*\d+[\).\:-]\s*", "", text).strip()
        text = re.sub(r"\s+", " ", text)
        if text:
            cleaned.append(text)
    if not cleaned:
        raise ValueError("The model did not return questions.")
    if not _is_opener(cleaned[0]):
        cleaned.insert(0, "Tell me about yourself.")
    unique: list[str] = []
    seen: set[str] = set()
    for question in cleaned:
        key = question.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(question[:500])
        if len(unique) == 7:
            break
    return InterviewScript(name, title, introduction[:500], tuple(unique), role_name)


def questions_input(job_description: str, resume_text: str, interviewer_name: str) -> str:
    return (
        f"INTERVIEWER NAME:\n{interviewer_name.strip()}\n\n"
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


def coach_from_payload(payload: Any, raw_text: str) -> tuple[str, str, str]:
    if not isinstance(payload, dict):
        raise ValueError("The model did not return an answer.")
    answer = str(payload.get("answer") or "").strip()
    guidance = str(payload.get("guidance") or "").strip()
    bridge = re.sub(r"\s+", " ", str(payload.get("bridge") or "")).strip()
    if not answer:
        answer = raw_text.strip()
    if not answer:
        raise ValueError("The model returned an empty answer.")
    if not guidance:
        guidance = "That already has a clear point. Next time, add the result in one sentence."
    if not bridge:
        bridge = "Thanks, that's useful. Let's keep going."
    return answer, guidance, bridge[:240]
