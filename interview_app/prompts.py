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

Return only a JSON object with the keys "role", "title", "role_brief", "introduction", and "questions".
No markdown fences.

role:
The name of this interview, taken from the job description. Use the job title and the organization when it is named, such as "CFO, Capital Markets at ATB". Do not include the word "interview".

role_brief:
What she says about the role before any question. Exactly 5 short lines, separated by newline characters.
Natural spoken language. Cover the core of the role: what the person is there to do, and what the job depends on.
No labels, no bullets, and no question. Do not say the interview will be easy.

introduction:
Three or four sentences she says before any question. She gives her name and title and welcomes the candidate. She says they have 3 minutes for each answer and can speak or type. She says they will have time at the end to ask her questions. Do not say the interview will be easy, light, or low pressure. No question in the introduction.

questions:
Exactly 25 short spoken questions. Each asks one thing and stays under 30 words.
Write them in this order:
1. The usual opening, in the spirit of "Tell me about yourself."
2. Why this role, or what drew them to it.
3. A question they can answer from their own experience.
4 and 5. Read the job description, then infer what similar roles in this organization are actually accountable for. Ask about the skill that matters most. If a concrete skill is required, such as SQL, question 4 asks them to rate that skill from 1 to 10, and question 5 is a simple practical check they can answer out loud. Do this for one important skill only.
6 through 14. Situational and behavioral questions: a disagreement, a moved deadline, a mistake, influencing someone, ownership, competing priorities, feedback, explaining something complex, and what good work looks like. Ask for a real situation, what they did, and the result.
15 through 18. More questions about what this role is accountable for, based on the job description and similar roles in the organization.
19. How they work when a team is remote, hybrid, or on site. Use whichever the job description implies. If it is silent, ask how they work with people who are not in the same place.
20. What they need from a manager.
21. A week when priorities change.
22. Their salary expectations for this role.
23. Where they want the role to take them.
24. What they would want finished in the first six months.
25. Anything about their experience they want understood before you close your questions.

Do not use question 25 to ask whether they have questions for you. That happens after these 25.
Sound like a person across a table. No numbering, no "as a hiring manager", and do not mention the résumé or the job description as documents. Do not say the interview will be easy.
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
One spoken sentence the interviewer will say before her next question, and only when they gave a real answer.
If they said nothing, or only filler such as "interesting", "okay", "sure", "yeah", or "no worries", return an empty string.
Do not reassure them. Do not say "no worries", "no problem", or "that's okay".
Do not comment on a missing answer. The next question should stand on its own.
Do not ask the next question inside the bridge.
""".strip()

INTERVIEWER_REPLY_INSTRUCTIONS = """
You are the interviewer answering a question the candidate just asked you.
Speak in the first person, as you would across the table, in 40 to 90 words.
Use the job description. Do not invent pay figures, headcount, or policies that are not in it.
If they ask about pay and the job description does not state it, say the recruiting team can walk through the range, and ask what they had in mind.
If their words are not a question, invite one specific question.
No headings, bullets, or labels.

Return only a JSON object with the string key "reply".
No markdown fences.
""".strip()

QUESTION_LIMIT = 25

CANDIDATE_OPENING = "That's the end of my questions. What would you like to ask me?"

FALLBACK_QUESTIONS = (
    "Tell me about yourself.",
    "What drew you to this role?",
    "Walk me through a piece of work that shows how you operate.",
    "Which skill in this role is your strongest, on a scale from 1 to 10?",
    "Give me a practical example of how you would use that skill here.",
    "Tell me about a time you disagreed with someone and how you handled it.",
    "Describe a situation where a deadline moved and what you did.",
    "Tell me about a time you made a mistake and what changed afterward.",
    "Describe a time you had to influence someone who did not report to you.",
    "Tell me about a time you took ownership of a problem that was not clearly yours.",
    "How do you decide what to do first when several things are urgent?",
    "What would you want to understand in your first month here?",
    "How have you worked with people in other functions?",
    "What part of this role will stretch you, and how will you handle that?",
    "Tell me about a result you are proud of and what you personally did.",
    "How do you like to receive feedback?",
    "Describe a time you had to explain a complex point to someone outside your field.",
    "What does good work look like to you in this kind of role?",
    "How do you work when the team is remote or hybrid?",
    "What do you need from a manager to do your best work?",
    "How do you handle a week when priorities change more than once?",
    "What are your salary expectations for this role?",
    "Where do you want this role to take you over the next couple of years?",
    "What would you want to have accomplished by the end of the first six months?",
    "Is there anything about your experience you want to make sure I understand?",
)

_FILLER_WORDS = {
    "a",
    "ah",
    "all",
    "alright",
    "an",
    "and",
    "awesome",
    "cool",
    "fine",
    "got",
    "great",
    "haha",
    "hm",
    "hmm",
    "huh",
    "i",
    "interesting",
    "it",
    "its",
    "just",
    "like",
    "lol",
    "mm",
    "mmm",
    "nice",
    "no",
    "nope",
    "of",
    "oh",
    "ok",
    "okay",
    "perfect",
    "pretty",
    "really",
    "right",
    "see",
    "so",
    "sure",
    "thank",
    "thanks",
    "that",
    "thats",
    "the",
    "to",
    "uh",
    "uhh",
    "um",
    "umm",
    "very",
    "well",
    "worry",
    "worries",
    "wow",
    "yeah",
    "yep",
    "yes",
    "you",
}


IMAGE_INSTRUCTIONS = (
    "Extract every readable word from this page. Keep headings and lists as plain lines. "
    "Return the document text only, with no commentary."
)


def _words(transcript: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", (transcript or "").lower())


def is_thin_transcript(transcript: str) -> bool:
    return len(_words(transcript)) < 5


def is_non_answer(transcript: str) -> bool:
    """True when they stayed silent or only offered filler such as 'interesting'."""
    words = _words(transcript)
    if not words:
        return True
    return all(word in _FILLER_WORDS for word in words)


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
    role_brief: str = ""


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


def _role_brief(value: str, role_name: str) -> str:
    raw = value.replace("\r\n", "\n").strip()
    lines = []
    for line in raw.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip(" -•*\t")
        cleaned = re.sub(r"^\d+[\).\:-]\s*", "", cleaned).strip()
        if cleaned and not re.search(r"\beasy\b", cleaned, re.IGNORECASE):
            lines.append(cleaned[:180])
    if not lines and raw:
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", raw)) if part.strip()]
        lines = [part[:180] for part in sentences if not re.search(r"\beasy\b", part, re.IGNORECASE)]
    if not lines:
        role = role_name or "the role"
        lines = [
            f"Before we start, a few words on {role}.",
            "The core of the job is the work this person is trusted to own.",
            "The team depends on that part being done with good judgment.",
            "The rest of the role hangs on that.",
            "We'll stay close to it as we talk.",
        ]
    return "\n".join(lines[:5])


def _without_easy(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = [part for part in parts if not re.search(r"\beasy\b", part, re.IGNORECASE)]
    return " ".join(kept).strip()


def _finish_sentence(text: str) -> str:
    base = text.rstrip()
    if base and base[-1] not in ".!?":
        base += "."
    return base


def _with_question_invite(introduction: str) -> str:
    lowered = introduction.lower()
    if "ask me" in lowered or "your questions" in lowered or "questions for me" in lowered:
        return introduction
    return f"{_finish_sentence(introduction)} You'll have time at the end to ask me questions.".strip()


def _with_answer_time(introduction: str) -> str:
    lowered = introduction.lower()
    if "3 minutes" in lowered or "three minutes" in lowered:
        return introduction
    return (
        f"{_finish_sentence(introduction)} "
        "You have 3 minutes for each answer. You can speak, or type it."
    ).strip()


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
    role_brief = _role_brief(str(payload.get("role_brief") or ""), role_name)
    title = re.sub(r"\s+", " ", str(payload.get("title") or payload.get("interviewer_title") or "")).strip()
    title = (title or "Hiring Manager")[:120]
    introduction = re.sub(r"\s+", " ", str(payload.get("introduction") or "")).strip()
    introduction = _without_easy(introduction)
    if name.lower() not in introduction.lower():
        introduction = f"Hi, I'm {name}, {title}. Thanks for making the time."
    introduction = _with_answer_time(_with_question_invite(introduction))
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
        if len(unique) == QUESTION_LIMIT:
            break
    for question in FALLBACK_QUESTIONS:
        if len(unique) == QUESTION_LIMIT:
            break
        if question.lower() in seen:
            continue
        seen.add(question.lower())
        unique.append(question)
    return InterviewScript(name, title, introduction[:900], tuple(unique[:QUESTION_LIMIT]), role_name, role_brief)


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


def coach_from_payload(payload: Any, raw_text: str, transcript: str = "") -> tuple[str, str, str]:
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
    if is_non_answer(transcript) or _is_reassurance(bridge):
        bridge = ""
    return answer, guidance, bridge[:240]


def _is_reassurance(bridge: str) -> bool:
    lowered = bridge.lower()
    return any(phrase in lowered for phrase in ("no worry", "no worries", "no problem", "that's okay", "that is okay"))
