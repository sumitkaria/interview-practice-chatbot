import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from docx import Document

from interview_app import auth, config, db, files, grok_client, mailer, prompts, ui

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def fresh_database(tmp_path):
    url = "sqlite:///" + (tmp_path / "test.db").resolve().as_posix()
    db.set_actor(None)
    db.init_db(url, force=True)
    yield
    db.set_actor(None)


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
    assert auth.valid_email("sumit@example.com")
    assert not auth.valid_email("not-an-email")
    assert not auth.valid_email("!@" + ("!." * 5000))
    with pytest.raises(auth.AuthError, match="shorter"):
        auth.register_user("Long", "long@example.com", "p" * 80)


def test_google_account_links_existing_email_and_can_be_new():
    created = db.create_password_user("Ada", "ada@example.com", auth.hash_password("long-password"))
    linked = db.upsert_google_user("ada@example.com", "Ada Lovelace", "sub-1")
    assert linked.id == created.id
    assert linked.google_sub == "sub-1"
    assert linked.password_hash == created.password_hash

    google_only = db.upsert_google_user("new@example.com", "", "sub-2")
    assert google_only.password_hash is None
    with pytest.raises(auth.AuthError, match="incorrect"):
        auth.login_user("new@example.com", "long-password")


def test_interview_keeps_a_snapshot_and_isolates_users():
    user = auth.register_user("Case", "case@example.com", "long-password")
    other = auth.register_user("Other", "other2@example.com", "long-password")
    first = db.create_interview(
        user.id,
        "Job A",
        "Resume A",
        ["Tell me about yourself.", "Why this role?"],
        interviewer_name="Amelia Ward",
        interviewer_title="Director of Analytics",
        introduction="Hi, I'm Amelia Ward.",
    )
    assert first.interviewer_name == "Amelia Ward"
    db.set_bridge(first.id, 1, "That was clear. Let's stay with the role.")
    assert db.latest_interview(user.id).bridges[1].startswith("That was clear")
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


def test_interview_history_keeps_older_interviews():
    user = auth.register_user("Case", "history@example.com", "long-password")
    first = db.create_interview(
        user.id,
        "CFO, Capital Markets\nATB Financial",
        "Resume A",
        ["Tell me about yourself."],
        role_name="CFO, Capital Markets at ATB Financial",
    )
    db.set_interview_status(first.id, "completed")
    second = db.create_interview(user.id, "Job B", "Resume B", ["Tell me about yourself."])
    rows = db.list_interviews(user.id)
    assert [row.id for row in rows] == [second.id, first.id]
    assert db.get_interview(first.id).status == "completed"
    assert ui.uploaded_name("ATB job description.docx", "Role text", "Pasted job description") == "ATB job description.docx"
    assert ui.uploaded_name("Pasted text", "Role text", "Pasted job description") == "Pasted job description"
    assert ui.uploaded_name("", "", "Pasted job description") == "Nothing uploaded yet"
    assert ui.interview_history_label(first).startswith("CFO, Capital Markets at ATB Financial · ")
    assert "in progress" in ui.interview_history_label(second)


def test_interview_name_comes_from_the_job_description():
    posted = prompts.interview_name(
        "CFO, Capital Markets\nATB Financial\n\nThe CFO leads the capital markets business."
    )
    assert posted == "CFO, Capital Markets at ATB Financial"
    labeled = prompts.interview_name("Job Title: Senior Analyst\nCompany: Northwind\n\nAbout the role.")
    assert labeled == "Senior Analyst at Northwind"
    assert prompts.interview_name("We are seeking a product manager to join the team.") == "product manager"
    assert prompts.interview_name("") == "Practice"
    interview = db.InterviewRecord(
        id="1",
        user_id="u",
        job_description="CFO, Capital Markets\nATB Financial\n",
        resume_text="resume",
        questions=("Tell me about yourself.",),
        current_index=0,
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    assert ui.practice_heading(None, interview) == "CFO, Capital Markets at ATB Financial"


def test_normalize_questions_and_coach_prompt():
    script = prompts.normalize_interview(
        {
            "title": "Director of Analytics, Northwind",
            "introduction": "Hi, I'm Amelia Ward. I lead analytics at Northwind.",
            "questions": ["2) Why this role?", "Tell me about yourself.", "Why this role?"],
        },
        interviewer_name="Amelia Ward",
    )
    assert script.interviewer_name == "Amelia Ward"
    assert script.questions[0] == "Tell me about yourself."
    assert script.questions[1] == "Why this role?"
    assert len(script.questions) == 25
    assert "3 minutes" in script.introduction
    assert "ask me" in script.introduction.lower()
    assert "easy" not in script.introduction.lower()
    assert "report to me" in script.role_brief
    assert "\n" not in script.role_brief
    assert prompts.heard_microphone("Sam, it's been a good morning")
    assert not prompts.heard_microphone("   ")
    assert prompts.MIC_TEST_QUESTION
    assert prompts.is_non_answer("")
    assert prompts.is_non_answer("Interesting.")
    assert prompts.is_non_answer("No worries")
    assert not prompts.is_non_answer("I led the migration for five years")

    fenced = prompts.parse_model_json('```json\n{"answer": "I did", "guidance": "Add a result"}\n```')
    answer, guidance, bridge = prompts.coach_from_payload(fenced, "", "Interesting")
    assert answer == "I did"
    assert "result" in guidance
    assert bridge == ""

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
    script = grok_client.generate_questions("job", "resume", cache_key="user-1", client=client)
    assert script.questions[0] == "Tell me about yourself."
    assert script.interviewer_name in prompts.INTERVIEWER_NAMES
    sent = client.responses.kwargs
    assert sent["model"] == "grok-4.7"
    assert sent["reasoning"] == {"effort": "low"}
    assert sent["store"] is False
    assert sent["prompt_cache_key"] == "user-1"

    coach = FakeClient('Sure. {"answer": "I built the hiring workflow.", "guidance": "Lead with the result."}')
    answer, guidance, bridge = grok_client.coach_answer(
        job_description="job",
        resume_text="resume",
        question="Tell me about yourself.",
        transcript="",
        cache_key="interview-1",
        client=coach,
    )
    assert answer == "I built the hiring workflow."
    assert guidance == "Lead with the result."
    assert bridge == ""


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


def test_prepare_database_url_rejects_sample_dots():
    with pytest.raises(config.DatabaseURLError, match="sample dots"):
        config.prepare_database_url("postgresql://...the line you copied...")
    with pytest.raises(config.DatabaseURLError, match="sample dots"):
        config.prepare_database_url("postgresql://...ep-cool.us-east-2.aws.neon.tech/neondb?sslmode=require")


def test_prepare_database_url_keeps_a_real_neon_string():
    raw = (
        "postgresql://neondb_owner:secret@ep-cool.us-east-2.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    prepared = config.prepare_database_url(f'"{raw}"')
    assert prepared.startswith("postgresql+psycopg://neondb_owner:secret@ep-cool.us-east-2.aws.neon.tech/neondb")
    assert "channel_binding=require" in prepared


def test_materials_survive_leaving_the_form_and_practice_saves_them():
    user = auth.register_user("Sumit", "materials@example.com", "correct horse")
    saved = db.save_profile(user.id, "Original job", "job.txt", "Original resume", "resume.txt")
    state = {
        "draft_marker": user.id + ":" + saved.updated_at.isoformat(),
        "job_draft": "Original job",
        "resume_draft": "Original resume",
        "job_source": "job.txt",
        "resume_source": "resume.txt",
    }
    ui.remember_drafts(state)
    del state["job_draft"]
    del state["resume_draft"]

    ui.ensure_drafts(user, db.get_profile(user.id), state)
    ui.restore_draft_widgets(state)
    assert state["job_draft"] == "Original job"
    assert state["resume_draft"] == "Original resume"

    state["job_draft"] = "Updated job description"
    state["resume_draft"] = "Updated resume"
    ui.remember_drafts(state)
    del state["job_draft"]
    del state["resume_draft"]
    updated = ui.persist_complete_drafts(user.id, db.get_profile(user.id), state)
    assert updated.job_description == "Updated job description"
    assert updated.resume_text == "Updated resume"
    assert not ui.drafts_differ(updated, state)


def test_blank_editor_does_not_erase_saved_materials():
    user = auth.register_user("Sumit", "keep-materials@example.com", "correct horse")
    db.save_profile(user.id, "Original job", "job.txt", "Original resume", "resume.txt", job_file_id="job-file", resume_file_id="resume-file")
    state = {
        "draft_marker": "stale",
        "job_draft": "",
        "resume_draft": "",
        "job_text": "",
        "resume_text": "",
        "job_source": "",
        "resume_source": "",
        "job_file_id": "",
        "resume_file_id": "",
    }
    ui.remember_drafts(state)
    ui.autosave_materials(user.id, state=state)
    saved = db.get_profile(user.id)
    assert saved.job_description == "Original job"
    assert saved.resume_text == "Original resume"
    assert saved.job_file_id == "job-file"
    assert saved.resume_file_id == "resume-file"
    assert state["job_draft"] == "Original job"
    assert state["resume_draft"] == "Original resume"

    state["job_draft"] = "Updated job only"
    ui.autosave_materials(user.id, state=state)
    saved = db.get_profile(user.id)
    assert saved.job_description == "Updated job only"
    assert saved.resume_text == "Original resume"


def test_blank_profile_is_restored_from_the_interview_or_file():
    user = auth.register_user("Sumit", "restore-materials@example.com", "correct horse")
    db.save_profile(user.id, "Director of Analytics", "role.txt", "Led the data team", "resume.txt")
    db.create_interview(user.id, "Director of Analytics", "Led the data team", ["Tell me about yourself."])
    db.save_profile(user.id, "", "", "", "")
    restored = ui.repair_saved_materials(user.id, db.get_profile(user.id))
    assert restored.job_description == "Director of Analytics"
    assert restored.resume_text == "Led the data team"

    other = auth.register_user("Case", "restore-file@example.com", "correct horse")
    db.store_file(other.id, "resume", "background.txt", b"Product manager resume")
    from_file = ui.repair_saved_materials(other.id, None)
    assert from_file is not None
    assert from_file.resume_text == "Product manager resume"
    assert from_file.job_description == ""


def test_prepare_database_url_fixes_a_leading_dot_when_credentials_exist():
    prepared = config.prepare_database_url(
        "postgresql://neondb_owner:secret@.ep-cool.us-east-2.aws.neon.tech/neondb?sslmode=require"
    )
    assert "@ep-cool.us-east-2.aws.neon.tech/" in prepared
    assert "@.ep-cool" not in prepared


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

    with pytest.raises(ValueError, match="could not be read"):
        files.extract_named_bytes("old.doc", b"not really a doc", None)
    with pytest.raises(ValueError, match="could not be read"):
        files.extract_named_bytes("slides.pptx", b"nope", None)


def test_sessions_are_revocable_and_legacy_cookies_do_not_sign_in():
    user = auth.register_user("Sam", "session@example.com", "long-password")
    token = auth.open_session(user.id, "secret", now=1_700_000_000)
    assert auth.authenticated_user_id(token, "secret", now=1_700_000_000) == user.id
    auth.revoke_session_token(token, "secret")
    assert auth.authenticated_user_id(token, "secret", now=1_700_000_000) is None
    legacy = auth.make_session_token(user.id, "secret", now=1_700_000_000)
    assert auth.read_session_token(legacy, "secret", now=1_700_000_000) == user.id
    assert auth.authenticated_user_id(legacy, "secret", now=1_700_000_000) is None


def test_login_locks_after_repeated_failures():
    auth.register_user("Sam", "lock@example.com", "long-password")
    for _ in range(auth.LOGIN_FAILURE_LIMIT):
        db.note_login_failure("lock@example.com", limit=auth.LOGIN_FAILURE_LIMIT, lock_seconds=60)
    with pytest.raises(auth.AuthError, match="Too many"):
        auth.login_user("lock@example.com", "long-password")
    db.clear_login_failures("lock@example.com")
    assert auth.login_user("lock@example.com", "long-password").email == "lock@example.com"


def test_contact_form_does_not_pretend_an_email_was_sent(monkeypatch):
    monkeypatch.setattr(mailer, "configured", lambda: False)
    assert mailer.deliver_contact("person@example.com", "Hello") is False

    sent = []
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(config, "contact_email", lambda: "")
    monkeypatch.setattr(mailer, "send_email", lambda *args: sent.append(args))
    assert mailer.deliver_contact("person@example.com", "Hello") is True
    assert sent[0][0] == "person@example.com"
    assert "Hello" in sent[0][2]


def test_contact_message_is_saved_for_the_account_owner():
    db.save_contact_message("person@example.com", "The microphone button did nothing.")
    messages = db.recent_contact_messages()
    assert messages
    assert messages[0][1] == "person@example.com"
    assert "microphone" in messages[0][2]


def test_sign_in_page_has_contact_and_hides_the_reset_note():
    source = (ROOT / "interview_app" / "ui.py").read_text()
    assert "Contact us" in source
    assert "Password reset by email is not set up" not in source
    assert "After you sign in, change the password from Account" not in source


def test_password_reset_without_mail_does_not_mention_account(monkeypatch):
    auth.register_user("Sam", "nomail@example.com", "long-password")
    monkeypatch.setattr("interview_app.mailer.configured", lambda: False)
    with pytest.raises(auth.AuthError, match="Contact us") as caught:
        auth.request_password_reset("nomail@example.com")
    assert "not set up" not in str(caught.value)


def test_password_reset_and_change_sign_out_other_sessions(monkeypatch):
    user = auth.register_user("Sam", "reset@example.com", "long-password")
    sent = {}

    def capture(recipient, subject, body):
        sent["body"] = body

    monkeypatch.setattr("interview_app.mailer.configured", lambda: True)
    monkeypatch.setattr("interview_app.mailer.send_email", capture)
    monkeypatch.setattr(
        "interview_app.mailer.app_link",
        lambda kind, token: f"https://example.test/?{kind}={token}",
    )
    auth.request_password_reset("missing@example.com")
    assert "body" not in sent
    auth.request_password_reset("reset@example.com")
    token = sent["body"].split("reset=")[1].split()[0]
    auth.reset_password(token, "newer-password")
    assert auth.login_user("reset@example.com", "newer-password").id == user.id

    session = auth.open_session(user.id, "secret", now=1_700_000_000)
    auth.change_password(user.id, "newer-password", "newest-password")
    assert auth.authenticated_user_id(session, "secret", now=1_700_000_000) is None
    assert auth.login_user("reset@example.com", "newest-password").id == user.id


def test_quota_files_export_and_owner(monkeypatch):
    monkeypatch.setattr(config, "max_interviews_per_day", lambda: 1)
    user = auth.register_user("Sam", "quota@example.com", "long-password")
    other = auth.register_user("Other", "other-quota@example.com", "long-password")
    first = db.create_interview(user.id, "Job", "Resume", ["Tell me about yourself."])
    with pytest.raises(db.QuotaExceeded):
        db.create_interview(user.id, "Job", "Resume", ["Tell me about yourself."])

    monkeypatch.setattr(config, "max_model_calls_per_day", lambda: 1)
    db.charge_model_call(user.id)
    with pytest.raises(db.QuotaExceeded):
        db.charge_model_call(user.id)

    file_id = db.store_file(user.id, "resume", "resume.pdf", b"resume-bytes")
    assert file_id
    assert db.read_file(file_id, user.id)[1] == b"resume-bytes"
    assert db.read_file(file_id, other.id) is None

    db.set_actor(other.id)
    assert db.get_interview(first.id) is None
    with pytest.raises(db.NotOwner):
        db.set_interview_status(first.id, "completed")
    db.set_actor(None)

    exported = db.export_account(user.id)
    assert exported["account"]["email"] == "quota@example.com"
    assert exported["interviews"][0]["id"] == first.id
    assert "password" not in json.dumps(exported).lower()
    db.delete_account(user.id)
    assert db.get_user(user.id) is None
    assert db.read_file(file_id, user.id) is None
    assert db.get_user(other.id) is not None


def test_pdf_page_cap_and_cloud_secrets(monkeypatch):
    class ManyPages:
        pages = [object()] * (files.MAX_PDF_PAGES + 1)

        def __init__(self, _buffer):
            pass

    monkeypatch.setattr("pypdf.PdfReader", ManyPages)
    with pytest.raises(ValueError, match="pages"):
        files.extract_named_bytes("long.pdf", b"%PDF", None)

    monkeypatch.setattr(config, "on_streamlit_cloud", lambda: True)

    def no_secret(name, default=None):
        return None

    monkeypatch.setattr(config, "secret", no_secret)
    assert "DATABASE_URL" in config.cloud_config_problem()


def test_voice_and_session_components_exist():
    voice = (ROOT / "interview_app/frontend/voice/index.html").read_text(encoding="utf-8")
    session = (ROOT / "interview_app/frontend/session/index.html").read_text(encoding="utf-8")
    assert "SpeechRecognition" in voice
    assert "speechSynthesis" in voice
    assert "maxSeconds" in voice
    assert "ip_session" in session
    assert "sessionStorage" in session
