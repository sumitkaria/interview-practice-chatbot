import io
import re
from pathlib import Path

import pytest
from docx import Document

from interview_app import auth, config, db, files, grok_client, prompts

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def fresh_database(tmp_path):
    url = "sqlite:///" + (tmp_path / "test.db").resolve().as_posix()
    db.init_db(url, force=True)
    yield


class FakeResponses:
    def __init__(self, text: str):
        self.text = text
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleResponse(self.text)


class SimpleResponse:
    def __init__(self, text: str):
        self.output_text = text


class FakeClient:
    def __init__(self, text: str):
        self.responses = FakeResponses(text)


class Upload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self.size = len(data)
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


def build_pdf(text: str) -> bytes:
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = f"BT /F1 18 Tf 40 100 Td ({safe}) Tj ET\n".encode("latin-1")
    objects = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 400 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n",
        b"4 0 obj<</Length %d>>stream\n" % len(content) + content + b"endstream\nendobj\n",
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
    ]
    chunks = [b"%PDF-1.4\n"]
    positions = []
    for obj in objects:
        positions.append(sum(len(chunk) for chunk in chunks))
        chunks.append(obj)
    xref_start = sum(len(chunk) for chunk in chunks)
    xref = [b"xref\n0 6\n", b"0000000000 65535 f \n"]
    xref.extend(f"{pos:010d} 00000 n \n".encode("ascii") for pos in positions)
    trailer = f"trailer<</Size 6/Root 1 0 R>>\nstartxref\n{xref_start}\n%%EOF\n".encode("ascii")
    return b"".join(chunks + xref + [trailer])


def test_password_session_and_separate_profiles():
    first = auth.register_user("Sumit Karia", "Sumit@Example.com", "correct horse")
    assert first.email == "sumit@example.com"
    assert first.name == "Sumit Karia"
    assert auth.login_user("sumit@example.com", "correct horse").id == first.id
    with pytest.raises(auth.AuthError):
        auth.login_user("sumit@example.com", "wrong-password")
    with pytest.raises(auth.AuthError):
        auth.register_user("", "sumit@example.com", "correct horse")

    db.save_profile(first.id, "Build hiring tools", "job.txt", "Product manager", "resume.txt")
    second = auth.register_user("", "other@example.com", "anotherpass")
    assert db.get_profile(second.id) is None
    saved = db.get_profile(first.id)
    assert saved is not None
    assert saved.resume_text == "Product manager"
    assert saved.job_source == "job.txt"

    token = auth.make_session_token(first.id, "secret", now=1_000)
    assert re.fullmatch(r"[A-Za-z0-9_-]+\.[a-f0-9]+", token)
    assert auth.read_session_token(token, "secret", now=1_000) == first.id
    assert auth.read_session_token(token, "other-secret", now=1_000) is None
    assert auth.read_session_token(token + "ab", "secret", now=1_000) is None
    assert auth.read_session_token(token, "secret", now=1_000 + auth.SESSION_TTL_SECONDS + 5) is None


def test_google_account_links_existing_email_and_can_be_new():
    created = db.create_password_user("Ada", "ada@example.com", auth.hash_password("long-password"))
    linked = db.upsert_google_user("ada@example.com", "Ada Lovelace", "sub-1")
    assert linked.id == created.id
    assert linked.google_sub == "sub-1"
    assert linked.password_hash == created.password_hash

    google_only = db.upsert_google_user("new@example.com", "", "sub-2")
    assert google_only.password_hash is None
    with pytest.raises(auth.AuthError, match="Google"):
        auth.login_user("new@example.com", "long-password")


def test_interview_keeps_a_snapshot_and_isolates_users():
    user = auth.register_user("Case", "case@example.com", "long-password")
    other = auth.register_user("Other", "other2@example.com", "long-password")
    first = db.create_interview(user.id, "Job A", "Resume A", ["Tell me about yourself.", "Why this role?"])
    db.save_turn(first.id, 0, "Tell me about yourself.", "I lead teams", "I lead product teams.", "Keep the example.", "manual")
    db.set_current_index(first.id, 1)
    saved = db.get_turn(first.id, 0)
    assert saved is not None
    assert saved.transcript == "I lead teams"
    db.set_interview_status(first.id, "completed")

    second = db.create_interview(user.id, "Job B", "Resume B", ["Tell me about yourself."])
    latest = db.latest_interview(user.id)
    assert latest is not None
    assert latest.id == second.id
    assert latest.job_description == "Job B"
    assert latest.status == "active"
    assert db.latest_interview(other.id) is None

    db.delete_turn(first.id, 0)
    assert db.get_turn(first.id, 0) is None
    assert db.list_turns(first.id) == []


def test_normalize_questions_and_coach_prompt():
    questions = prompts.normalize_questions(
        {"questions": ["2) Why this role?", "Tell me about yourself.", "Why this role?"]}
    )
    assert questions[0] == "Tell me about yourself."
    assert questions[1] == "Why this role?"
    assert len(questions) == 2

    fenced = prompts.parse_model_json('```json\n{"answer": "I did", "guidance": "Add a result"}\n```')
    answer, guidance = prompts.coach_from_payload(fenced, "")
    assert answer == "I did"
    assert "result" in guidance

    thin = prompts.coach_input("job", "resume", "Tell me about yourself.", "um")
    assert "too thin" in thin
    full = prompts.coach_input("job", "resume", "Tell me about yourself.", "I spent four years building hiring tools for clinics")
    assert "Stay close" in full
    assert prompts.is_thin_transcript("um hello")
    assert not prompts.is_thin_transcript("I spent four years building hiring tools for clinics and teams")


def test_grok_requests_use_the_flagship_model(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    monkeypatch.delenv("GROK_MODEL", raising=False)
    monkeypatch.delenv("GROK_REASONING_EFFORT", raising=False)
    client = FakeClient('{"questions": ["What hiring problem did you solve?", "How do you work with recruiters?"]}')
    questions = grok_client.generate_questions("job", "resume", cache_key="user-1", client=client)
    assert questions[0] == "Tell me about yourself."
    sent = client.responses.kwargs
    assert sent["model"] == "grok-4.7"
    assert sent["reasoning"] == {"effort": "low"}
    assert sent["store"] is False
    assert sent["prompt_cache_key"] == "user-1"

    coach = FakeClient('Sure. {"answer": "I built the hiring workflow.", "guidance": "Lead with the result."}')
    answer, guidance = grok_client.coach_answer(
        job_description="job",
        resume_text="resume",
        question="Tell me about yourself.",
        transcript="",
        cache_key="interview-1",
        client=coach,
    )
    assert answer == "I built the hiring workflow."
    assert guidance == "Lead with the result."


def test_missing_grok_key(monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    with pytest.raises(grok_client.GrokNotConfigured):
        grok_client.generate_questions("job", "resume", cache_key="user")


def test_database_url_normalization():
    assert config.normalize_database_url("postgres://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert (
        config.normalize_database_url("postgresql://user:pass@host/db?sslmode=require")
        == "postgresql+psycopg://user:pass@host/db?sslmode=require"
    )
    assert config.normalize_database_url("postgresql+psycopg://host/db") == "postgresql+psycopg://host/db"


def test_extracts_common_file_types():
    text = files.extract_named_bytes("notes.txt", b"\xef\xbb\xbfHiring manager\n", None)
    assert text == "Hiring manager"

    html = b"<html><body><style>p{}</style><h1>Engineer</h1><p>Built data tools.</p></body></html>"
    assert "Engineer" in files.extract_named_bytes("page.html", html, None)
    assert "p{}" not in files.extract_named_bytes("page.html", html, None)

    rtf = br"{\rtf1\ansi Hello RTF resume.\par Built tools.}"
    extracted_rtf = files.extract_named_bytes("background.rtf", rtf, None)
    assert "Hello RTF resume." in extracted_rtf

    pdf = files.extract_named_bytes("resume.pdf", build_pdf("Product manager resume"), None)
    assert "Product manager resume" in pdf

    document = Document()
    document.add_paragraph("Staff designer")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Skill"
    table.rows[0].cells[1].text = "Research"
    buffer = io.BytesIO()
    document.save(buffer)
    docx_text = files.extract_named_bytes("resume.docx", buffer.getvalue(), None)
    assert "Staff designer" in docx_text
    assert "Research" in docx_text

    seen = {}

    def read_image(data: bytes, mime: str) -> str:
        seen["mime"] = mime
        seen["size"] = len(data)
        return "Scanned resume text"

    combined, source = files.extract_uploads(
        [Upload("scan.PNG", b"png-bytes"), Upload("notes.md", b"Led a team")],
        read_image,
    )
    assert seen == {"mime": "image/png", "size": 9}
    assert "Scanned resume text" in combined
    assert "Led a team" in combined
    assert source == "scan.PNG, notes.md"

    with pytest.raises(ValueError, match="docx"):
        files.extract_named_bytes("old.doc", b"not really a doc", None)
    with pytest.raises(ValueError, match="supported"):
        files.extract_named_bytes("slides.pptx", b"nope", None)


def test_voice_and_session_components_exist():
    voice = (ROOT / "interview_app/frontend/voice/index.html").read_text(encoding="utf-8")
    session = (ROOT / "interview_app/frontend/session/index.html").read_text(encoding="utf-8")
    assert "SpeechRecognition" in voice
    assert "speechSynthesis" in voice
    assert "maxSeconds" in voice
    assert "ip_session" in session
    assert "sessionStorage" in session
