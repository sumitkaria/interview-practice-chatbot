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
A short spoken introduction of the role, the way she would say it across the table. Four to six sentences in one paragraph.
No line breaks, no bullets, and no labels such as "reports to" or "team size".
Cover the core of the job in plain language. Then who the person would report to, about how big the team is, and why the seat is open.
If the job description does not say those, still give a reasonable picture connected to this kind of role, as how the job sits, not as a checklist.
Close with one sentence on what she will be listening for, so the candidate knows how to answer.
Use contractions. Do not say the interview will be easy. Do not ask a question.

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
You write the answer a strong candidate would say out loud, then one short feedback note.

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
The only feedback for this question. Second person, 18 to 36 words, two sentences at most.
Make it cheerful and pleasant to read, so they can start the next question without feeling stressed.
First sentence: one warm thing that already worked, specific to what they just said.
Second sentence: exactly one small thing to try next time. Do not add a second tip, a list, or a full rewrite.
Do not say they failed, missed the question, or that the interviewer has no reason to stay.
If they did not really answer, stay just as brief and kind, and offer one easy way to open this kind of question.
Use fresh wording every time. Do not repeat a sentence, an opener, or a suggestion already listed under feedback given this session.
Shape, not words to copy: "That was warm and easy to follow. Next time, open with your current work."

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

MIC_TEST_QUESTION = "Just to check the microphone, say your first name and how your day is going."

SMALL_TALK_OPENER = "How's your day going so far?"

SMALL_TALK_INSTRUCTIONS = """
You are a woman interviewing in North America. She already asked how their day is going. This is the only small talk.

Reply in one short sentence to what they just said. Stay on that. Do not ask another question.
Do not bring up the weather, the trip, coffee, the weekend, or the city.
Do not announce that the interview is starting. Do not say "no worries" or that the interview will be easy.
If they said almost nothing, one plain sentence is enough, such as "All right."

Return only a JSON object with the keys "reply" and "wrap_up".
wrap_up is always true.
No markdown fences.
""".strip()

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


def heard_microphone(transcript: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9]", transcript or ""))


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
    pieces = []
    for line in raw.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip(" -•*\t")
        cleaned = re.sub(r"^\d+[\).\:-]\s*", "", cleaned).strip()
        if cleaned and not re.search(r"\beasy\b", cleaned, re.IGNORECASE):
            pieces.append(cleaned)
    text = re.sub(r"\s+", " ", " ".join(pieces)).strip()
    if len(text) < 80:
        role = role_name or "this role"
        text = (
            f"The heart of {role} is the work the rest of the group is counting on someone to own. "
            "You'd report to me, with a small team around you, closer to a handful of people than a large department. "
            "The seat is open because that work has grown past what the current group can cover. "
            "As we talk, I'm listening for how you'd take that on day to day."
        )
    return text[:900]


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
    prior_feedback: list[str] | None = None,
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
        f"EARLIER ANSWERS IN THIS SESSION:\n{history}\n\n"
        f"FEEDBACK ALREADY GIVEN THIS SESSION:\n{_format_prior_feedback(prior_feedback or [])}\n"
    )


def _format_prior_feedback(notes: list[str]) -> str:
    cleaned = []
    for note in notes:
        text = re.sub(r"\s+", " ", note or "").strip()
        if text and text != "candidate-question":
            cleaned.append(text[:240])
    if not cleaned:
        return "None yet."
    return "\n".join(f"- {note}" for note in cleaned[-12:])


def _format_prior(prior: list[tuple[str, str]]) -> str:
    if not prior:
        return "None."
    blocks = []
    for question, transcript in prior[-5:]:
        spoken = (transcript or "").strip()[:400] or "[nothing captured]"
        blocks.append(f"Question: {question.strip()}\nSaid: {spoken}")
    return "\n\n".join(blocks)


_STRESS_RE = re.compile(
    r"(didn['’]t actually|did not actually|no reason to|"
    r"doesn['’]t have a reason|does not have a reason|"
    r"you failed|you missed|weakness|unfortunately|not an answer|off topic)",
    re.IGNORECASE,
)

_SUGGESTION_MARKS = (
    "next time",
    "try ",
    "try to",
    "add ",
    "open with",
    "lead with",
    "close with",
    "start with",
    "name ",
    "mention ",
    "put the",
    "say what",
)

_OPENERS = (
    "That was easy to listen to.",
    "You sound warm and clear.",
    "Nice and steady.",
    "That came across as friendly.",
    "Good energy there.",
    "Pleasant to hear.",
    "You kept it human, which helps.",
    "Clear and calm.",
    "That felt genuine.",
    "Easy to follow.",
    "You sound ready for this.",
    "Lovely tone.",
    "That was light and confident.",
    "Smooth and easy to hear.",
    "You sound thoughtful there.",
    "Bright and clear.",
    "That landed well.",
    "Calm and easy to trust.",
    "A friendly start.",
    "That was kind and clear.",
    "You sound at ease.",
    "Warm and straightforward.",
    "That was pleasant to read.",
    "A steady, likable answer.",
    "You sound composed.",
)

_TIPS = (
    "Next time, open with where you are now.",
    "Try closing with the result in one line.",
    "Lead with the point, then one thing you did.",
    "Add why it fits this role, in a single line.",
    "Name one real situation and how it turned out.",
    "Start with the outcome, then how you got there.",
    "Add one detail only you would know.",
    "Say what changed because of your work.",
    "Try one concrete example from your own path.",
    "Put the point in the first sentence.",
    "Mention one outcome you are glad about.",
    "Next time, tie it to this role in one line.",
    "Open with one earlier chapter of your work.",
    "Next time, close with what you would do in this seat.",
    "Next time, give one number or fact from that work.",
    "Next time, say who you partnered with.",
    "Start with the decision you made.",
    "Name the constraint, then what you chose.",
    "Next time, end with what you learned.",
    "Next time, share one moment that shows how you work.",
    "Next time, bring in the person you helped.",
    "Say what you would keep and what you would change.",
    "Open with the work you are proudest of.",
    "Add the timeline in a few words.",
    "Close with how the team felt afterward.",
)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


def _norm_note(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def _is_suggestion(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(mark in lowered for mark in _SUGGESTION_MARKS)


def _opener_key(text: str) -> str:
    for sentence in _sentences(text):
        if not _is_suggestion(sentence):
            return _norm_note(sentence)
    return ""


def _tip_key(text: str) -> str:
    for sentence in _sentences(text):
        if _is_suggestion(sentence):
            return _norm_note(sentence)
    return ""


def _too_close(left: str, right: str) -> bool:
    a = set(_norm_note(left).split())
    b = set(_norm_note(right).split())
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.8


def _seed(question: str, transcript: str, salt: str) -> int:
    return sum(ord(ch) for ch in f"{question}|{transcript}|{salt}")


def _unused(options: tuple[str, ...], used: set[str], question: str, transcript: str, salt: str) -> str:
    start = _seed(question, transcript, salt) % len(options)
    for offset in range(len(options)):
        choice = options[(start + offset) % len(options)]
        if _norm_note(choice) not in used:
            return choice
    return options[start]


def _short_clause(sentence: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", sentence).strip()
    if len(cleaned.split()) <= limit:
        return _finish_sentence(cleaned)
    chunks = [part.strip() for part in cleaned.split(",") if part.strip()]
    if len(chunks) >= 2 and len(chunks[0].split()) <= 3:
        kept = ", ".join(chunks[:2])
    elif chunks:
        kept = chunks[0]
    else:
        kept = cleaned
    if len(kept.split()) > limit:
        kept = " ".join(kept.split()[:limit])
    return _finish_sentence(kept)


def _compose_feedback(text: str) -> tuple[str, str, str]:
    sentences = [sentence for sentence in _sentences(text) if not _STRESS_RE.search(sentence)]
    warm = [_short_clause(sentence, 22) for sentence in sentences if not _is_suggestion(sentence)]
    tips = [_short_clause(sentence, 16) for sentence in sentences if _is_suggestion(sentence)]
    opener = warm[0] if warm else ""
    tip = tips[0] if tips else ""
    note = f"{opener} {tip}".strip()
    words = note.split()
    if len(words) > 42:
        note = _finish_sentence(" ".join(words[:42]))
    return note, opener, tip


def _fresh_feedback(opener: str, tip: str, question: str, transcript: str, prior: list[str]) -> str:
    used_openers = {_opener_key(item) for item in prior if item.strip()}
    used_tips = {_tip_key(item) for item in prior if item.strip()}
    chosen_opener = opener or _unused(_OPENERS, used_openers, question, transcript, "opener")
    chosen_tip = tip or _unused(_TIPS, used_tips, question, transcript, "tip")
    if _norm_note(chosen_opener) == _norm_note(chosen_tip):
        chosen_tip = _unused(_TIPS, used_tips | {_norm_note(chosen_tip)}, question, transcript, "tip-alt")
    return f"{_finish_sentence(chosen_opener)} {_finish_sentence(chosen_tip)}".strip()


def shape_feedback(
    text: str,
    *,
    question: str = "",
    transcript: str = "",
    prior_notes: list[str] | None = None,
) -> str:
    """One brief, cheerful note that does not repeat feedback already given."""
    prior = [note.strip() for note in (prior_notes or []) if note and note.strip()]
    note, opener, tip = _compose_feedback(text)
    if not note:
        return _fresh_feedback("", "", question, transcript, prior)
    if not prior:
        return note
    opener_used = bool(opener) and any(opener and _norm_note(opener) == _opener_key(item) for item in prior)
    tip_used = bool(tip) and any(tip and _norm_note(tip) == _tip_key(item) for item in prior)
    close = any(_norm_note(note) == _norm_note(item) or _too_close(note, item) for item in prior)
    if not opener_used and not tip_used and not close:
        return note
    return _fresh_feedback(
        "" if opener_used or close else opener,
        "" if tip_used or close else tip,
        question,
        transcript,
        prior,
    )


def coach_from_payload(
    payload: Any,
    raw_text: str,
    transcript: str = "",
    *,
    question: str = "",
    prior_notes: list[str] | None = None,
) -> tuple[str, str, str]:
    if not isinstance(payload, dict):
        raise ValueError("The model did not return an answer.")
    answer = str(payload.get("answer") or "").strip()
    guidance = str(payload.get("guidance") or "").strip()
    bridge = re.sub(r"\s+", " ", str(payload.get("bridge") or "")).strip()
    if not answer:
        answer = raw_text.strip()
    if not answer:
        raise ValueError("The model returned an empty answer.")
    guidance = shape_feedback(guidance, question=question, transcript=transcript, prior_notes=prior_notes)
    if is_non_answer(transcript) or _is_reassurance(bridge):
        bridge = ""
    return answer, guidance, bridge[:240]


def _is_reassurance(bridge: str) -> bool:
    lowered = bridge.lower()
    return any(phrase in lowered for phrase in ("no worry", "no worries", "no problem", "that's okay", "that is okay"))
