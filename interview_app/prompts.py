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
Sound like a person across a table. No numbering, no "as a hiring manager", and do not mention the resume or the job description as documents. Do not say the interview will be easy.
""".strip()

COACH_INSTRUCTIONS = """
You write the answer this candidate would give if they were calm, specific, and brief, then a note that keeps what worked and repairs one weakness.

A hiring manager is deciding three things: can they do the work, will they do the work, and will they fit. The answer should make one of those obvious. It should sound like a person across a table in Canada, not like a worksheet, a LinkedIn post, or a coach reading headings.

The user message names an ANSWER SHAPE. Follow that shape, including its length. Do not announce the shape, and do not say Situation, Task, Action, Result, Skills, STAR, STARS, PREP, PPE, or SEAT out loud.

How the answer should sound:
- The first sentence is the point. No "great question", "absolutely", "of course", "so basically", or "I would say that".
- Contractions and plain words. Mix a short sentence with a longer one. No headings, bullets, labels, or brackets.
- Say "I" for what they did. Use "we" only for the shared setting, then say what their part was.
- Spend the words on what they did and what changed. One sentence of setup is enough. If the setup runs long, cut it.
- Use a number, percentage, or time saved only when that figure is in the background or in what they just said. Never invent an employer, title, date, metric, tool, product launch, award, headcount, or quote. A concrete result without a made-up percentage is the honest version.
- Never speak badly of a past employer, manager, or coworker. Describe the work problem, not a person's character. Keep the tone forward-looking.
- Do not use these phrases: leverage, passionate, synergy, think outside the box, hit the ground running, wear many hats, people person, perfectionist, go-getter, circle back, move the needle, at the end of the day, team player, dynamic, results-driven, I care too much.
- Pick one episode from the background. Prefer a result they drove, a time they led, a disagreement they settled, a mistake they repaired, or a time they influenced someone who did not report to them. Do not reuse an episode already told in EARLIER ANSWERS unless this question cannot be answered without it.
- Name something specific from the job description: a duty, a tool, a stakeholder, or the problem the seat exists to solve. If the organization is named and you know a stable public fact about what it does, you may use that fact. Do not invent news.
- For a weakness, use a real work habit that would not sink this job, then the system they already use to manage it. Not a virtue in disguise.
- For why they want the role, start from the organization's work or a problem in the job description, not from what they want for their own career.
- For why they should be hired, name the hard part of the role, match two skills to it with proof, and you may close with one question about that work. The question is about the job, not about whether the interviewer liked the answer.

If their words already answer the question, keep their meaning, examples, and claims. You may cut repetition, shorten the setup, and move the point to the first sentence. Do not add a fact they did not give you, and do not swap in a different story.
If the recording is empty, off topic, or too thin, write an honest answer from the background. If the background has no fitting episode, say what they would do in this role based on the closest real work. Do not invent a scene.

Return only a JSON object with the string keys "answer", "guidance", and "bridge".
No markdown fences.

answer:
First person, spoken, at the length given in ANSWER SHAPE.
No stage directions such as "(pause)".

guidance:
Second person, 45 to 80 words.
Name the kind of question in plain words, with no framework acronyms.
Start with the specific line or fact that already worked. Then one fix: the result was missing, the setup was too long, they said "we" for their own action, they never tied it to this job, the weakness had no system, they criticized a person, or they listed several points instead of one.
If they did not answer, say that plainly and give them the first sentence to open with next time.
You may tell them to pause before that first sentence so it does not fill with "um" or "like".

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


_ANSWER_SHAPES = {
    "career_story": (
        "Career story, 150 to 190 words. Past trajectory in a sentence or two, then the present skills "
        "that match this job description, one achievement with a result, and what they would take on in this seat. "
        "Do not recap every job. Do not open with childhood or a slogan."
    ),
    "why_role": (
        "Why this role, 90 to 140 words. Open from the organization's work or a specific problem in the job "
        "description, not from what they want for their own career. Then the part of their background already aimed "
        "at that problem, with one result, and what they would do in the seat."
    ),
    "why_hire": (
        "Why hire them, 110 to 150 words. First the hard part of this role, in words from the job description. "
        "Then two skills that meet that hard part, each with one proof from their background. "
        "You may close with one short question about that same work. Do not ask if they liked the answer."
    ),
    "weakness": (
        "A weakness, 70 to 110 words. A real work habit that would not cause this job to fail. "
        "Not a joke, and not a virtue in disguise. Then the system they already use, and one sign it is working."
    ),
    "strength": (
        "One strength this job needs, 80 to 120 words. Prove it with one example and a result. No list of adjectives."
    ),
    "salary": (
        "Pay, 40 to 70 words. If they named a figure, keep it. If they did not, do not invent one. "
        "Talk about the scope and say they would want the range for that scope. No apology and no joke."
    ),
    "mistake": (
        "A mistake, 110 to 150 words. Own it in the first sentence. What they did next, the change in how they work, "
        "and a later result of that change. No one else is at fault."
    ),
    "conflict": (
        "A disagreement, 120 to 160 words. The issue, not the other person's character. What they said or did, "
        "the outcome, and the working relationship afterward."
    ),
    "rating": (
        "A rating, under 80 words. Keep the number they chose and do not raise it. One piece of proof, then the gap "
        "they would close on the job if the number is short of the top. If they gave no number, do not invent one."
    ),
    "technical": (
        "A practical check, under 120 words. A correct answer in plain spoken words. One example of how they have "
        "used it if the background shows that. Do not lecture."
    ),
    "plan": (
        "The early months, 80 to 120 words. One priority, why this job needs that first, and how they would know it "
        "worked. If they were asked what they would learn, name one thing and why it changes how they would start. "
        "Not a list."
    ),
    "direction": (
        "Where the role goes, 70 to 110 words. A near-term path that serves this work, not a title they want for "
        "themselves."
    ),
    "leaving": (
        "Why they are looking, 60 to 100 words. Forward-looking, tied to this role. Nothing negative about a current "
        "or past employer."
    ),
    "manager": (
        "What they need from a manager, 70 to 110 words. One need, one time that helped the work, and how that would "
        "look here. Not a list."
    ),
    "priorities": (
        "Competing priorities, 80 to 120 words. State the rule they use, the reason, one week it mattered, then the "
        "rule again in fresh words. One rule only."
    ),
    "remote": (
        "Working apart, 70 to 110 words. One habit they use with people who are not beside them, one example, and "
        "why that habit holds the work together."
    ),
    "feedback": (
        "Feedback, 60 to 100 words. One way they want it, and one time they used it to change the work."
    ),
    "achievement": (
        "A result, 120 to 160 words. Lead with the outcome, then one sentence of context, then what they personally "
        "did. The outcome should be the kind of result this role is hired to produce."
    ),
    "closing": (
        "One last point, 70 to 110 words. A piece of their background that matters for this role and is not already "
        "in EARLIER ANSWERS. If the relevant stories are used, say the single point they most want remembered."
    ),
    "hypothetical": (
        "What they would do, 100 to 140 words. The steps in this role, in order. Ground one step in work they have "
        "already done if the background has it. Do not invent a past crisis."
    ),
    "behavioral": (
        "One story, 120 to 170 words, about a minute and a half spoken. One sentence of context, one sentence on "
        "what was theirs to do, then most of the words on the steps they took, in order. Close with what changed, "
        "and one clause on the skill this job is hiring for. Use a number only if it is already in the materials."
    ),
    "open": (
        "An open question, 70 to 110 words. Pause is for the person; the answer still picks one point. "
        "State it, give one reason, one example from their background, then say the point again in fresh words and "
        "tie it to this role. Do not turn it into a long story, and do not list several traits."
    ),
}


def answer_shape(question: str) -> str:
    """Pick the spoken structure for this interview question."""
    q = re.sub(r"\s+", " ", (question or "").lower()).strip()
    if not q:
        return "open"
    if re.search(r"\b(1\s*to\s*10|1-10|out of 10|on a scale|scale from|rate your)\b", q):
        return "rating"
    if re.search(r"\b(salary|compensation|pay expectation)\b", q) or "how much do you" in q:
        return "salary"
    if "about yourself" in q or "introduce yourself" in q or re.search(r"\babout you\b", q):
        return "career_story"
    if re.search(r"walk me through your (background|career|experience|r[eé]sum[eé])", q):
        return "career_story"
    if any(phrase in q for phrase in ("why are you leaving", "why did you leave", "why are you looking", "why you're looking")):
        return "leaving"
    if "why should" in q or "hire you" in q or "why you over" in q:
        return "why_hire"
    if any(
        phrase in q
        for phrase in (
            "why this",
            "why do you want",
            "what drew",
            "interested in",
            "why our",
            "why us",
            "why the company",
            "why the role",
        )
    ):
        return "why_role"
    if any(phrase in q for phrase in ("weakness", "stretch you", "development area", "struggle with", "not good at")):
        return "weakness"
    if any(phrase in q for phrase in ("mistake", "you failed", "a failure", "went wrong", "regret")):
        return "mistake"
    if any(phrase in q for phrase in ("disagre", "conflict", "push back", "pushed back")):
        return "conflict"
    if re.search(r"\b(six months|6 months|first month|90 days|ninety days|first 30|first six)\b", q) or any(
        phrase in q for phrase in ("want finished", "have accomplished", "want to understand in your first")
    ):
        return "plan"
    if any(phrase in q for phrase in ("take you", "five years", "next couple", "where do you want", "career goal")):
        return "direction"
    if any(phrase in q for phrase in ("from a manager", "your manager", "a good manager", "need from me")):
        return "manager"
    if "priorit" in q or "several things" in q:
        return "priorities"
    if any(phrase in q for phrase in ("remote", "hybrid", "on site", "onsite", "same place", "not in the same")):
        return "remote"
    if "feedback" in q:
        return "feedback"
    if any(phrase in q for phrase in ("practical", "how would you use", " sql", "query")) or q.startswith("sql"):
        return "technical"
    if any(phrase in q for phrase in ("strength", "strongest", "best at", "what are you good")):
        return "strength"
    if any(phrase in q for phrase in ("proud", "a result", "accomplishment")):
        return "achievement"
    if any(
        phrase in q
        for phrase in (
            "make sure i understand",
            "make sure you understand",
            "anything about your experience",
            "anything else about",
            "before you close",
            "before i close",
            "before we close",
        )
    ):
        return "closing"
    if any(phrase in q for phrase in ("what would you do", "how would you handle", "how would you")):
        return "hypothetical"
    if any(
        phrase in q
        for phrase in (
            "tell me about a time",
            "describe a time",
            "describe a situation",
            "give me an example",
            "give us an example",
            "walk me through a",
            "how have you",
            "have you ever",
            "ownership",
            "influenc",
            "deadline",
        )
    ):
        return "behavioral"
    return "open"


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
            "Write a full honest answer from the background. Do not invent a scene."
        )
    else:
        check = (
            "The transcript conveys an answer. Stay close to what the candidate meant. "
            "Do not replace their story with a shinier one."
        )
    history = _format_prior(prior or [])
    shape = answer_shape(question)
    return (
        f"JOB DESCRIPTION:\n{job_description.strip()}\n\n"
        f"CANDIDATE BACKGROUND:\n{resume_text.strip()}\n\n"
        f"INTERVIEW QUESTION:\n{question.strip()}\n\n"
        f"ANSWER SHAPE: {shape}\n{_ANSWER_SHAPES[shape]}\n\n"
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


_SILLY_OPENER = re.compile(
    r"^(?:"
    r"that(?:'s| is) a (?:great|good|excellent) question[.!]?\s*"
    r"|great question[.!]?\s*"
    r"|absolutely[.!,]\s*"
    r"|of course[.!,]\s*"
    r"|sure[.!,]\s*"
    r"|so,?\s+basically,?\s*"
    r"|i would say that\s+"
    r")",
    re.IGNORECASE,
)

_FRAME_LABEL = re.compile(
    r"(?:^|(?<=[.!?]\s))(?:situation|task|action|result|skills|star|stars|prep|ppe|seat)\s*:\s*",
    re.IGNORECASE,
)


def polish_spoken_answer(answer: str) -> str:
    """Drop worksheet labels and stock openings that make a spoken answer sound rehearsed."""
    original = re.sub(r"\s+", " ", (answer or "")).strip()
    text = original
    if not text:
        return ""
    previous = None
    while previous != text:
        previous = text
        text = _SILLY_OPENER.sub("", text).strip()
    text = _FRAME_LABEL.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return original
    return text


def coach_from_payload(payload: Any, raw_text: str, transcript: str = "") -> tuple[str, str, str]:
    if not isinstance(payload, dict):
        raise ValueError("The model did not return an answer.")
    answer = polish_spoken_answer(str(payload.get("answer") or ""))
    guidance = str(payload.get("guidance") or "").strip()
    bridge = re.sub(r"\s+", " ", str(payload.get("bridge") or "")).strip()
    if not answer:
        answer = polish_spoken_answer(raw_text)
    if not answer:
        raise ValueError("The model returned an empty answer.")
    if not guidance:
        guidance = "That already has a clear point. Next time, add the result in one sentence and tie it to this role."
    if is_non_answer(transcript) or _is_reassurance(bridge):
        bridge = ""
    return answer, guidance, bridge[:240]


def _is_reassurance(bridge: str) -> bool:
    lowered = bridge.lower()
    return any(phrase in lowered for phrase in ("no worry", "no worries", "no problem", "that's okay", "that is okay"))
