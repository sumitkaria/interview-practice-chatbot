"""Instructions and parsers for interview questions and coaching."""

from __future__ import annotations

import json
import random
import re
import secrets
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

Every session needs its own questions. Do not recycle a stock list. Do not repeat, and do not lightly reword, anything listed under ALREADY USED FOR THIS ROLE.
Ground each question in this job, so another session for the same role would not ask it again.
Use the session angle to vary the situations. Do not mention the angle or the session cue.

Return only a JSON object with the keys "role", "title", "role_brief", "introduction", "small_talk", and "questions".
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

small_talk:
One creative small-talk question she asks after the microphone check and before the role brief. Under 18 words.
It should feel specific, like something a person would actually ask across a table.
Do not ask how their day is going, how they are, or anything about the microphone or their name.
Do not mention the weather, coffee, the commute, the weekend, or the city.
Do not mention the job, the résumé, or the interview.

introduction:
Three or four sentences she says before any question. She gives her name and title and welcomes the candidate. She says they have 3 minutes for each answer and can speak or type. She says they will have time at the end to ask her questions. Do not say the interview will be easy, light, or low pressure. No question in the introduction.

questions:
Exactly 25 short spoken questions. Each asks one thing and stays under 30 words.
Write them in this order:
1. An opening in the spirit of asking them to introduce themselves. Phrase it freshly for this session. Do not use the sentence "Tell me about yourself."
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
Second person, 40 to 80 words. Always write this. Never return an empty string.
If they gave a real answer, begin with what already sounded credible. If one thing could be sharper, name it and how to say it better. If nothing needs repair, do not invent a weakness. Encourage them and name what to keep doing.
If they said nothing or only filler, be warm. Tell them a pause is fine, then explain how to handle this kind of question next time. Do not scold.

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

MIC_TEST_QUESTION = "Just to check the microphone, say your first name."

SMALL_TALK_INSTRUCTIONS = """
You are a woman interviewing in North America. She just asked one short, friendly small-talk question. This is the only small talk.

Reply in one short sentence to what they just said. Stay on that. Do not ask another question.
Do not ask how their day is going. Do not bring up the weather, the trip, coffee, the weekend, or the city.
Do not announce that the interview is starting. Do not say "no worries" or that the interview will be easy.
If they said almost nothing, one warm sentence is enough, such as "Glad you said it."

Return only a JSON object with the keys "reply" and "wrap_up".
wrap_up is always true.
No markdown fences.
""".strip()

MORE_QUESTION_INSTRUCTIONS = """
You are adding spoken interview questions for a woman interviewing in North America.
Return only a JSON object with the key "questions".
No markdown fences.

Write exactly the number of new questions requested. Each asks one thing and stays under 30 words.
Do not repeat, rephrase, or lightly edit any question under ALREADY USED.
Ground them in this job. Use the session angle so they would not fit a different session. Do not mention the angle.
Sound like a person across a table. No numbering, and do not mention the résumé or the job description as documents.
""".strip()

VARIETY_BRIEFS = (
    "Lean into a decision they made before they had all the facts.",
    "Lean into a stakeholder who wanted a different outcome.",
    "Lean into how they explain the work to someone outside it.",
    "Lean into a plan that changed after they had already started.",
    "Lean into the standard they refuse to drop when time is short.",
    "Lean into work they picked up because nobody else did.",
    "Lean into how they can tell the work actually helped.",
    "Lean into a time they changed their own mind.",
)

SMALL_TALK_BANK = (
    "Have you read or watched anything lately that stuck with you?",
    "What's something you're looking forward to this month, outside of work?",
    "Did anything make you laugh this week?",
    "What's a meal you've been meaning to cook or order?",
    "Is there a hobby you wish you had more time for?",
    "What's the last thing you learned just because you were curious?",
    "Have you picked up any new music lately?",
    "What's a tiny win from this week that nobody else would notice?",
    "If you had a free hour after this, how would you spend it?",
    "What's something kind someone did for you recently?",
    "Have you been making anything just for yourself lately?",
    "What's a skill you'd like to get a little better at, just for fun?",
    "What's the best small piece of advice you've heard this year?",
    "Is there a story you've been telling friends lately?",
    "What's one thing that made this week feel different from the last?",
)

OPENING_QUESTIONS = (
    "Walk me through how you got to the work you do now.",
    "Give me the short version of who you are and the work you do.",
    "What should I know about you before we get into the role?",
    "How would you introduce the work you are proudest of?",
    "Tell me how you ended up doing this kind of work.",
)

_EXTRA_PATTERNS = (
    "When {role} gets messy, what do you take on first?",
    "Tell me about a time you changed your mind about a piece of work.",
    "What would a recent teammate say you always make room for?",
    "How do you know a piece of work is actually finished?",
    "Describe a time you had to slow a project down, and why.",
    "What question do you wish people asked you about your work?",
    "Tell me about a handoff that went badly and what you do now.",
    "How do you keep a promise when the facts change underneath it?",
    "What did you learn from the last person who disagreed with you?",
    "Which part of {role} would still be interesting on a hard week?",
    "Tell me about a decision you would make differently today.",
    "How do you bring someone along who is skeptical of your plan?",
    "What do you check before you call a piece of work ready?",
    "Describe a time you noticed a problem nobody had named yet.",
    "How do you divide your attention when two leaders want different things?",
    "What standard do you hold even when the deadline is close?",
    "Tell me about a time you asked for help earlier than you wanted to.",
    "How do you leave a project easier for the next person?",
    "What would you want this team to stop doing in your first month?",
    "Describe a time you translated a complex point for a non-expert.",
    "How do you choose what not to do?",
    "Tell me about a result that took longer than you expected.",
    "What does trust look like between you and a manager?",
    "How do you share news you know people will not like?",
    "What skill are you still deliberately building for {role}?",
    "Tell me about a meeting where you changed the outcome.",
    "How do you recover after something ships and it is wrong?",
    "What would you want me to notice about how you work?",
    "Describe a time you protected the quality of the work.",
    "How should a team use your first ninety days in {role}?",
    "Thinking about {angle}, what example from your own work should I hear?",
    "Where has {angle} already shown up in work like {role}?",
    "Tell me about a tradeoff you made while doing work like {role}.",
    "What would you want finished in {role} that a job description would miss?",
    "How do you decide who needs to know when the plan shifts?",
    "Describe a time you inherited work and made it yours.",
    "What do you do in the first hour when a priority lands on you?",
    "Tell me about a time you were the calm person in the room.",
    "How do you keep your own work visible without talking over people?",
    "What is a story from your background that {role} still needs?",
)

_SPARE_QUESTIONS = (
    "Tell me about a time you had to start over on something you cared about.",
    "What do you do when you realize you are the only one who sees the risk?",
    "How do you decide which detail is worth a conversation?",
    "Describe a time you made the work simpler for someone else.",
    "What's a belief about your work that you used to hold and don't anymore?",
    "Tell me about a moment you chose the slower path on purpose.",
    "How do you keep going when the feedback is vague?",
    "What would you want a new teammate to copy from how you work?",
    "Tell me about a promise you kept after it got inconvenient.",
    "How do you tell the difference between a real problem and a noisy one?",
    "What's something {role} would ask of you that your last role did not?",
    "Tell me about a time {angle} changed what you did next.",
)

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
    small_talk: str = ""


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


def is_opening_question(question: str) -> bool:
    return _is_opener(question)


def _is_opener(question: str) -> bool:
    lowered = question.lower()
    return any(
        hint in lowered
        for hint in (
            "about yourself",
            "about you",
            "who you are",
            "how you got",
            "introduce",
            "the work you do",
            "ended up",
            "proudest",
            "know about you",
        )
    )


def material_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().casefold())


def question_key(question: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", (question or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def session_variety() -> str:
    angle = random.choice(VARIETY_BRIEFS)
    return f"{angle} Session cue {secrets.token_hex(3)}."


def encouraging_note(transcript: str) -> str:
    if is_non_answer(transcript):
        return (
            "It's fine to pause. When you take this question again, start with the point in one sentence, "
            "then one real example of what you did and how it turned out. "
            "You have more to draw on than it feels like in the quiet, and you can do this."
        )
    return (
        "That already gives an interviewer something solid to hold onto. "
        "Keep opening with the point and closing with the result. You're on the right track."
    )


def feedback_text(transcript: str, guidance: str) -> str:
    cleaned = " ".join((guidance or "").split())
    return cleaned or encouraging_note(transcript)


def small_talk_is_stale(text: str) -> bool:
    lowered = (text or "").lower()
    return any(phrase in lowered for phrase in _STALE_SMALL_TALK)


def acceptable_small_talk(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if "?" not in cleaned or len(cleaned) < 12 or len(cleaned) > 180:
        return False
    if cleaned.lower() == MIC_TEST_QUESTION.lower():
        return False
    return not small_talk_is_stale(cleaned)


def fresh_small_talk() -> str:
    choices = [line for line in SMALL_TALK_BANK if acceptable_small_talk(line)]
    return random.choice(choices or list(SMALL_TALK_BANK))


def normalize_interview(payload: Any, interviewer_name: str, *, avoid: list[str] | None = None) -> InterviewScript:
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
    cleaned = _clean_question_items(payload)
    if not cleaned:
        raise ValueError("The model did not return questions.")
    selected = _dedupe_keeping_order(cleaned, list(avoid or []))
    return InterviewScript(
        name,
        title,
        introduction[:900],
        tuple(selected),
        role_name,
        role_brief,
        _small_talk_from_payload(payload),
    )


def extend_interview(script: InterviewScript, payload: Any, *, avoid: list[str] | None = None) -> InterviewScript:
    incoming = _clean_question_items(payload)
    merged = _dedupe_keeping_order([*script.questions, *incoming], list(avoid or []))
    return _with_questions(script, merged)


def fill_interview(script: InterviewScript, *, avoid: list[str] | None = None, variety: str = "") -> InterviewScript:
    blocked = list(avoid or [])
    chosen = _dedupe_keeping_order(list(script.questions), blocked)
    used = _used_keys(chosen, blocked)
    if not chosen or not _is_opener(chosen[0]):
        opener = _fresh_opener(used)
        if opener:
            chosen = [opener, *chosen]
            used.add(question_key(opener))
    role = _spoken_role(script.role_name)
    angle = _angle_phrase(variety)
    rng = random.Random(variety or "session")
    patterns = list(_EXTRA_PATTERNS)
    rng.shuffle(patterns)
    extras = [_render_extra(pattern, role, angle) for pattern in patterns]
    extras.extend(FALLBACK_QUESTIONS)
    for question in extras:
        if len(chosen) >= QUESTION_LIMIT:
            break
        text = re.sub(r"\s+", " ", question).strip()[:500]
        key = question_key(text)
        if not key or key in used:
            continue
        used.add(key)
        chosen.append(text)
    for question in _SPARE_QUESTIONS:
        if len(chosen) >= QUESTION_LIMIT:
            break
        text = _render_extra(question, role, angle)
        key = question_key(text)
        if not key or key in used:
            continue
        used.add(key)
        chosen.append(text[:500])
    return _with_questions(script, chosen)


def questions_input(
    job_description: str,
    resume_text: str,
    interviewer_name: str,
    *,
    avoid: list[str] | None = None,
    variety: str = "",
) -> str:
    return (
        f"INTERVIEWER NAME:\n{interviewer_name.strip()}\n\n"
        f"{_avoid_block(avoid)}"
        f"SESSION ANGLE:\n{variety.strip() or 'A fresh conversation.'}\n"
        "Use the angle so this set is different from every other session. Do not mention the angle or the cue.\n\n"
        f"JOB DESCRIPTION:\n{job_description.strip()}\n\n"
        f"CANDIDATE BACKGROUND:\n{resume_text.strip()}\n"
    )


def more_questions_input(
    job_description: str,
    resume_text: str,
    *,
    needed: int,
    avoid: list[str] | None = None,
    variety: str = "",
) -> str:
    return (
        f"NEW QUESTIONS NEEDED:\n{max(1, needed)}\n\n"
        f"{_avoid_block(avoid)}"
        f"SESSION ANGLE:\n{variety.strip() or 'A fresh conversation.'}\n\n"
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
    if is_non_answer(spoken) or is_thin_transcript(spoken):
        check = (
            "The transcript is empty or too thin to convey an answer. "
            "Write a full answer from the background and explain how to handle the question. "
            "Always include encouraging guidance, even when there is nothing else to correct."
        )
    else:
        check = (
            "The transcript conveys an answer. Stay close to what the candidate meant. "
            "If nothing needs repair, encourage them instead of inventing a weakness."
        )
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
    guidance = feedback_text(transcript, guidance)
    if is_non_answer(transcript) or _is_reassurance(bridge):
        bridge = ""
    return answer, guidance, bridge[:240]


def _is_reassurance(bridge: str) -> bool:
    lowered = bridge.lower()
    return any(phrase in lowered for phrase in ("no worry", "no worries", "no problem", "that's okay", "that is okay"))


_STALE_SMALL_TALK = (
    "how was your day",
    "how's your day",
    "hows your day",
    "how is your day",
    "how your day",
    "how's it going",
    "hows it going",
    "how is it going",
    "how are you",
    "how're you",
    "howre you",
    "microphone",
    "your first name",
    "the weather",
    "coffee",
    "the weekend",
    "your commute",
    "this weekend",
)


def _clean_question_items(payload: Any) -> list[str]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("questions", [])
    else:
        return []
    if not isinstance(items, list):
        return []
    cleaned: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("question") or item.get("text") or "")
        else:
            text = str(item)
        text = re.sub(r"^\s*\d+[\).\:-]\s*", "", text).strip()
        text = re.sub(r"\s+", " ", text)
        if text:
            cleaned.append(text[:500])
    return cleaned


def _used_keys(*groups: list[str] | tuple[str, ...]) -> set[str]:
    keys: set[str] = set()
    for group in groups:
        for question in group:
            key = question_key(question)
            if key:
                keys.add(key)
    return keys


def _fresh_opener(used: set[str]) -> str | None:
    for opener in OPENING_QUESTIONS:
        key = question_key(opener)
        if key and key not in used:
            return opener
    return None


def _place_opener(questions: list[str], used: set[str]) -> list[str]:
    for index, question in enumerate(questions):
        if _is_opener(question):
            if index == 0:
                return questions
            return [question, *questions[:index], *questions[index + 1 :]]
    opener = _fresh_opener(used)
    if not opener:
        return questions
    return [opener, *questions]


def _dedupe_keeping_order(questions: list[str], avoid: list[str]) -> list[str]:
    used = _used_keys(avoid)
    chosen: list[str] = []
    for question in questions:
        key = question_key(question)
        if not key or key in used:
            continue
        used.add(key)
        chosen.append(question[:500])
        if len(chosen) == QUESTION_LIMIT:
            break
    placed = _place_opener(chosen, used)
    return placed[:QUESTION_LIMIT]


def _with_questions(script: InterviewScript, questions: list[str]) -> InterviewScript:
    return InterviewScript(
        script.interviewer_name,
        script.interviewer_title,
        script.introduction,
        tuple(questions[:QUESTION_LIMIT]),
        script.role_name,
        script.role_brief,
        script.small_talk,
    )


def _render_extra(pattern: str, role: str, angle: str) -> str:
    return pattern.replace("{role}", role).replace("{angle}", angle)


def _spoken_role(role_name: str) -> str:
    role = re.sub(r"\s+", " ", (role_name or "").strip())
    return role[:80] or "this role"


def _angle_phrase(variety: str) -> str:
    text = re.sub(r"session cue [0-9a-f]+\.?", "", (variety or ""), flags=re.IGNORECASE)
    text = re.sub(r"^lean into\s+", "", text.strip(), flags=re.IGNORECASE).strip(" .")
    return text or "careful judgment"


def _avoid_block(avoid: list[str] | None) -> str:
    lines: list[str] = []
    for question in avoid or []:
        text = " ".join((question or "").split())
        if text:
            lines.append(f"- {text}")
        if len(lines) == 150:
            break
    listing = "\n".join(lines) or "None yet."
    return (
        f"ALREADY USED FOR THIS ROLE:\n{listing}\n"
        "Do not ask any of these again, and do not ask a light rewording of them.\n\n"
    )


def _small_talk_from_payload(payload: Any) -> str:
    if isinstance(payload, dict):
        text = str(payload.get("small_talk") or payload.get("small_talk_question") or "")
        text = re.sub(r"\s+", " ", text).strip().strip('"')
        if acceptable_small_talk(text):
            return text
    return fresh_small_talk()
