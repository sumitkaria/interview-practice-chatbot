"""Streamlit screens for sign-in, materials, and spoken practice."""

from __future__ import annotations

import html
import secrets

import streamlit as st

from interview_app import auth, config, db, files, grok_client
from interview_app.components import interview_voice, session_bridge

MAX_ANSWER_SECONDS = 180
_VIEW_PREFIXES = ("pending_answer_", "attempt_", "typed_")
_DRAFT_FIELDS = (
    ("job_draft", "job_text", "job_description", "job_source"),
    ("resume_draft", "resume_text", "resume_text", "resume_source"),
)
_VIEW_KEYS = {
    "draft_marker",
    "job_draft",
    "resume_draft",
    "job_text",
    "resume_text",
    "job_source",
    "resume_source",
    "job_upload_sig",
    "resume_upload_sig",
    "job_upload_sig_error",
    "resume_upload_sig_error",
    "confirm_restart",
    "just_saved",
}


def main() -> None:
    inject_css()
    try:
        db.init_db()
    except config.DatabaseURLError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:
        st.error("The database could not be opened.")
        st.caption(safe_db_message(exc))
        st.stop()

    if st.session_state.get("logged_out") and st.session_state.get("want_google_logout"):
        nonce = str(st.session_state.get("logout_nonce") or "")
        result = session_bridge(action="clear", nonce=nonce)
        if result and result.get("action") == "clear" and str(result.get("nonce") or "") == nonce:
            st.logout()
        st.info("Signing out…")
        st.stop()

    render_session_cookie()
    user = current_user()
    if user is None:
        cloud_storage_notice()
        render_login()
        return
    render_app(user)


BRAND = """
<div class="brand">
  <svg class="mark" viewBox="0 0 48 48" aria-hidden="true">
    <rect width="48" height="48" rx="12" fill="#1B3A34"/>
    <path d="M11 16.5h13.2c2.6 0 4.3 1.6 4.3 3.9 0 2.2-1.6 3.7-4 3.9l-2.2 4.2-1.2-4.1H11c-2.4 0-4-1.6-4-3.9s1.6-4 4-4z" fill="#F3E6C8"/>
    <path d="M23.2 23.2h12.2c2.3 0 3.8 1.4 3.8 3.4 0 1.9-1.4 3.3-3.5 3.4l-1.8 3.6-1.1-3.5h-6.2c-2.1 0-3.5-1.4-3.5-3.4 0-2 1.5-3.5 3.1-3.5z" fill="#B8893D"/>
  </svg>
  <div class="brand-copy">
    <div class="brand-name">Interview Practice</div>
    <div class="brand-tag">Arrive ready.</div>
  </div>
</div>
"""


def inject_css() -> None:
    st.markdown(
        """
        <style>
        @import url("https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600;700&display=swap");
        :root {
            --ink: #1C1917;
            --forest: #1B3A34;
            --brass: #A6843D;
            --paper: #F6F3EC;
            --card: #FFFcf7;
            --line: #D9D1C3;
            --font: "Source Sans 3", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        }
        html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
            background: var(--paper);
            color: var(--ink);
            font-family: var(--font);
        }
        [data-testid="stHeader"] { background: transparent; }
        #MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; }
        .block-container {
            max-width: 760px;
            padding-top: 2.2rem;
            padding-bottom: 4rem;
        }
        [data-testid="stAppViewContainer"] h1,
        [data-testid="stAppViewContainer"] h2,
        [data-testid="stAppViewContainer"] h3,
        [data-testid="stAppViewContainer"] p,
        [data-testid="stAppViewContainer"] label,
        [data-testid="stAppViewContainer"] button,
        [data-testid="stAppViewContainer"] input,
        [data-testid="stAppViewContainer"] textarea,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] button {
            font-family: var(--font);
        }
        h1 {
            color: var(--ink);
            font-size: 2.15rem !important;
            font-weight: 650 !important;
            letter-spacing: -0.03em;
        }
        h2, h3 { color: var(--ink); font-weight: 650; letter-spacing: -0.02em; }
        [data-testid="stCaptionContainer"] { color: #3C3832; }
        [data-testid="stMain"] .stButton > button,
        [data-testid="stMain"] .stFormSubmitButton > button {
            border-radius: 999px;
            border: 1px solid var(--forest);
            background: var(--forest);
            color: #F6F3EC;
            font-weight: 600;
        }
        [data-testid="stMain"] .stButton > button:hover,
        [data-testid="stMain"] .stFormSubmitButton > button:hover {
            background: #142E29;
            color: #F6F3EC;
            border-color: #142E29;
        }
        [data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 12px;
            color: var(--ink);
        }
        [data-testid="stFileUploader"] {
            background: var(--card);
            border: 1px dashed #C4BBA9;
            border-radius: 16px;
            padding: 0.35rem 0.6rem 0.2rem;
        }
        [data-testid="stFileUploaderDropzoneInstructions"] {
            font-size: 0 !important;
            line-height: 0;
        }
        [data-testid="stFileUploaderDropzoneInstructions"]::after {
            content: "10MB max file size";
            font-size: 0.92rem;
            line-height: 1.4;
            color: #3C3832;
            font-weight: 500;
        }
        [data-testid="stSidebar"] {
            background: #E5EEE9;
            border-right: 1px solid #D3DDD7;
        }
        [data-testid="stSidebar"] .stButton > button {
            background: transparent;
            color: var(--ink);
            border: 1px solid transparent;
            border-radius: 10px;
            text-align: left;
            justify-content: flex-start;
            font-weight: 600;
            box-shadow: none;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"],
        [data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {
            background: var(--forest);
            color: #F6F3EC;
            border-color: var(--forest);
        }
        .brand { display: flex; gap: 0.75rem; align-items: center; margin: 0.2rem 0 1rem; }
        .brand .mark { width: 42px; height: 42px; flex: none; }
        .brand-name { font-size: 1.05rem; font-weight: 700; letter-spacing: -0.02em; color: var(--ink); line-height: 1.15; }
        .brand-tag { color: var(--brass); font-size: 0.92rem; font-weight: 600; margin-top: 0.12rem; }
        .account-name { font-weight: 650; color: var(--ink); margin-top: 0.8rem; }
        .account-email { color: #24312C; font-size: 0.92rem; margin-bottom: 0.85rem; }
        .files { margin: 0.4rem 0 0.8rem; }
        .file {
            color: #14221E;
            font-weight: 650;
            font-size: 0.95rem;
            line-height: 1.35;
            padding: 0.28rem 0;
        }
        .studio {
            background: var(--card);
            border: 1px solid var(--line);
            border-left: 4px solid var(--brass);
            border-radius: 18px;
            padding: 1.25rem 1.35rem 1.05rem;
            margin: 0.2rem 0 1rem;
        }
        .studio .who { margin-bottom: 0.75rem; }
        .studio .name { font-size: 1.2rem; font-weight: 700; line-height: 1.2; color: var(--ink); }
        .studio .role { color: var(--forest); font-weight: 600; font-size: 0.95rem; margin-top: 0.12rem; }
        .studio .aside { color: #2E3330; font-size: 1.02rem; line-height: 1.5; margin: 0 0 0.8rem; }
        .studio .ask { font-size: 1.65rem; font-weight: 650; line-height: 1.3; letter-spacing: -0.03em; margin: 0 0 0.85rem; color: var(--ink); }
        .studio .count { color: var(--brass); font-size: 0.78rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def safe_db_message(exc: Exception) -> str:
    text = str(exc)
    if "label empty" in text or "idna" in text.lower():
        return (
            "DATABASE_URL still contains the sample dots, so the database address starts with a period. "
            "Replace the whole value with the Neon connection string that starts with postgresql://."
        )
    if "@" in text or "password" in text.lower():
        return "Check DATABASE_URL and whether the database server is reachable."
    return text[:300]


def cloud_storage_notice() -> None:
    if not config.on_streamlit_cloud():
        return
    if config.uses_local_sqlite():
        st.warning(
            "This app is using temporary storage. Add DATABASE_URL in Streamlit secrets "
            "(a free Neon Postgres database works) or accounts and uploads disappear when the app restarts."
        )
    if not config.auth_cookie_secret_is_configured():
        st.warning(
            "Add AUTH_COOKIE_SECRET in Streamlit secrets so password sign-in keeps working after a restart."
        )


def render_session_cookie() -> None:
    if st.session_state.get("logged_out"):
        session_bridge(action="clear", nonce=str(st.session_state.get("logout_nonce") or ""))
        return
    token = st.session_state.get("pending_cookie")
    if token:
        session_bridge(action="set", token=token, max_age=auth.SESSION_TTL_SECONDS)


def read_cookie() -> str:
    try:
        return st.context.cookies.get(auth.COOKIE_NAME, "") or ""
    except Exception:
        return ""


def google_identity() -> dict | None:
    if not config.google_auth_configured():
        return None
    try:
        if not st.user.is_logged_in:
            return None
        email = str(st.user["email"] or "").strip().lower()
        sub = str(st.user["sub"] or "").strip()
        name = str(st.user["name"] or "").strip() if "name" in st.user else ""
    except Exception:
        return None
    if not email or not sub:
        return None
    return {"email": email, "sub": sub, "name": name}


def current_user():
    google = google_identity()
    if google is not None and not st.session_state.get("logged_out"):
        try:
            user = db.upsert_google_user(google["email"], google["name"], google["sub"])
        except db.AuthLinkError as exc:
            st.error(str(exc))
            st.stop()
        st.session_state.auth_user_id = user.id
        remember_user(user.id)
        return user
    if st.session_state.get("logged_out"):
        return None
    user_id = st.session_state.get("auth_user_id")
    if not user_id:
        token = read_cookie()
        user_id = auth.read_session_token(token, config.auth_cookie_secret()) if token else None
        if user_id:
            st.session_state.auth_user_id = user_id
    if not user_id:
        return None
    user = db.get_user(user_id)
    if user is None:
        st.session_state.auth_user_id = None
        return None
    remember_user(user.id)
    return user


def clear_user_views() -> None:
    for key in list(st.session_state.keys()):
        if key in _VIEW_KEYS or key.startswith(_VIEW_PREFIXES):
            del st.session_state[key]
    st.session_state.upload_nonce = int(st.session_state.get("upload_nonce", 0)) + 1


def remember_user(user_id: str) -> None:
    if st.session_state.get("active_user_id") == user_id:
        return
    clear_user_views()
    st.session_state.active_user_id = user_id


def request_logout() -> None:
    st.session_state.logged_out = True
    st.session_state.want_google_logout = google_identity() is not None
    st.session_state.logout_nonce = secrets.token_hex(8)
    st.session_state.auth_user_id = None
    st.session_state.pending_cookie = None
    clear_user_views()
    st.rerun()


def render_login() -> None:
    st.markdown(BRAND, unsafe_allow_html=True)
    st.caption("Your résumé and the role stay with your account.")
    if config.google_auth_configured():
        if st.button("Continue with Google", use_container_width=True):
            try:
                st.login()
            except Exception:
                st.error("Google sign-in is not available. Check the [auth] section in Streamlit secrets.")
        st.caption("Or use an email and password.")
    else:
        st.caption("Google sign-in is not set up yet. Create an account with email and password.")

    mode = st.radio(
        "Account",
        ["Log in", "Create account"],
        horizontal=True,
        label_visibility="collapsed",
    )
    with st.form("credentials"):
        name = st.text_input("Name") if mode == "Create account" else ""
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password") if mode == "Create account" else ""
        submitted = st.form_submit_button(
            "Create account" if mode == "Create account" else "Log in",
            use_container_width=True,
        )
    if not submitted:
        return
    try:
        if mode == "Create account":
            if password != confirm:
                st.error("Those passwords do not match.")
                return
            user = auth.register_user(name, email, password)
        else:
            user = auth.login_user(email, password)
    except auth.AuthError as exc:
        st.error(str(exc))
        return
    st.session_state.logged_out = False
    st.session_state.want_google_logout = False
    st.session_state.auth_user_id = user.id
    st.session_state.pending_cookie = auth.make_session_token(user.id, config.auth_cookie_secret())
    st.rerun()


def render_app(user: db.UserRecord) -> None:
    profile = db.get_profile(user.id)
    ensure_drafts(user, profile)
    ready = profile_ready(profile)
    if "section" not in st.session_state:
        st.session_state.section = "Practice" if ready else "Materials"
    render_sidebar(user, profile)
    section = st.session_state.get("section") or "Practice"
    if st.session_state.pop("just_saved", False):
        st.success("Saved. It will be here the next time you sign in.")
    if section == "Practice" and not ready:
        st.title("Practice")
        st.write("Add the role and your résumé in Materials first.")
        return
    if section == "Materials":
        st.title("Materials")
        st.caption("Add the role and your résumé. They stay with your account.")
        restore_draft_widgets(st.session_state)
        render_materials(user, profile)
        return
    latest = db.latest_interview(user.id)
    st.title(practice_heading(profile, latest))
    profile = persist_complete_drafts(user.id, profile)
    render_practice(user, profile)


def practice_heading(profile: db.ProfileRecord | None, interview: db.InterviewRecord | None = None) -> str:
    if interview is not None:
        named = (interview.role_name or "").strip()
        if not named and interview.job_description.strip():
            named = prompts.interview_name(interview.job_description)
        if named and named != "Practice":
            return named
    if profile is not None and profile.job_description.strip():
        return prompts.interview_name(profile.job_description)
    return "Practice"


def profile_ready(profile: db.ProfileRecord | None) -> bool:
    return bool(profile and profile.job_description.strip() and profile.resume_text.strip())


def ensure_drafts(user: db.UserRecord, profile: db.ProfileRecord | None, state=None) -> None:
    """Keep material text available after the Materials form is closed.

    The text boxes use widget keys. Streamlit removes those keys when Practice
    is showing, so a second copy is kept under a key that is not a widget.
    """
    state = st.session_state if state is None else state
    remember_drafts(state)
    marker = user.id + ":" + (profile.updated_at.isoformat() if profile else "new")
    if state.get("draft_marker") != marker:
        state["draft_marker"] = marker
        for widget_key, durable_key, attr, source_key in _DRAFT_FIELDS:
            value = getattr(profile, attr) if profile else ""
            state[widget_key] = value
            state[durable_key] = value
            state[source_key] = getattr(profile, source_key) if profile else ""
        return
    for widget_key, durable_key, attr, _source_key in _DRAFT_FIELDS:
        if durable_key not in state:
            state[durable_key] = getattr(profile, attr) if profile else ""


def remember_drafts(state) -> None:
    for widget_key, durable_key, _attr, _source_key in _DRAFT_FIELDS:
        if widget_key in state:
            state[durable_key] = state.get(widget_key) or ""


def restore_draft_widgets(state) -> None:
    for widget_key, durable_key, _attr, _source_key in _DRAFT_FIELDS:
        if widget_key not in state and durable_key in state:
            state[widget_key] = state[durable_key]


def current_draft(state, widget_key: str) -> str:
    for key, durable_key, _attr, _source_key in _DRAFT_FIELDS:
        if key == widget_key:
            if widget_key in state:
                return state.get(widget_key) or ""
            return state.get(durable_key) or ""
    return ""


def render_sidebar(user: db.UserRecord, profile: db.ProfileRecord | None) -> None:
    section = st.session_state.get("section") or "Practice"
    with st.sidebar:
        st.markdown(BRAND, unsafe_allow_html=True)
        if st.button(
            "Practice",
            type="primary" if section == "Practice" else "secondary",
            use_container_width=True,
            key="nav_practice",
        ):
            st.session_state.section = "Practice"
            st.rerun()
        if st.button(
            "Materials",
            type="primary" if section == "Materials" else "secondary",
            use_container_width=True,
            key="nav_materials",
        ):
            st.session_state.section = "Materials"
            st.rerun()
        st.markdown(
            "<div class='account-name'>"
            + html.escape(user.name or user.email)
            + "</div><div class='account-email'>"
            + html.escape(user.email)
            + "</div>",
            unsafe_allow_html=True,
        )
        if profile_ready(profile):
            job_name = profile.job_source if profile.job_source and profile.job_source != "Pasted text" else "Job description"
            resume_name = (
                profile.resume_source
                if profile.resume_source and profile.resume_source != "Pasted text"
                else "Résumé"
            )
            st.markdown(
                "<div class='files'>"
                f"<div class='file'>{html.escape(job_name)}</div>"
                f"<div class='file'>{html.escape(resume_name)}</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        if st.button("Log out", type="secondary", use_container_width=True):
            request_logout()
        cloud_storage_notice()
        if config.uses_local_sqlite() and not config.on_streamlit_cloud():
            st.caption("Saving to a local database file. Set DATABASE_URL to use Postgres.")


def render_materials(user: db.UserRecord, profile: db.ProfileRecord | None) -> None:
    nonce = st.session_state.get("upload_nonce", 0)
    reader = image_reader_for(user.id)
    render_material_editor(
        title="The role",
        upload_label="Upload a job description",
        paste_label="Or paste it here",
        draft_key="job_draft",
        source_key="job_source",
        sig_key="job_upload_sig",
        upload_key=f"job_files_{user.id}_{nonce}",
        reader=reader,
    )
    render_material_editor(
        title="Your résumé",
        upload_label="Upload a résumé",
        paste_label="Or paste it here",
        draft_key="resume_draft",
        source_key="resume_source",
        sig_key="resume_upload_sig",
        upload_key=f"resume_files_{user.id}_{nonce}",
        reader=reader,
    )
    if st.button("Save", type="primary", use_container_width=True):
        save_materials(user.id)


def render_material_editor(
    *,
    title: str,
    upload_label: str,
    paste_label: str,
    draft_key: str,
    source_key: str,
    sig_key: str,
    upload_key: str,
    reader,
) -> None:
    st.subheader(title)
    uploads = st.file_uploader(
        upload_label,
        accept_multiple_files=True,
        key=upload_key,
        help="10MB max file size",
    )
    apply_upload(uploads, sig_key, draft_key, source_key, reader)
    error = st.session_state.get(sig_key + "_error")
    if error:
        st.error(error)
    st.text_area(paste_label, key=draft_key, height=220)
    draft = st.session_state.get(draft_key) or ""
    source = st.session_state.get(source_key) or ""
    if source:
        st.caption(f"{source} · {len(draft):,} characters")
    elif draft:
        st.caption(f"{len(draft):,} characters")


def image_reader_for(user_id: str):
    def read(data: bytes, mime: str) -> str:
        return grok_client.extract_document_text(data, mime, cache_key=user_id)

    return read


def apply_upload(uploads, sig_key: str, draft_key: str, source_key: str, reader) -> None:
    items = list(uploads or [])
    signature = tuple((item.name, item.size) for item in items)
    if not signature or signature == st.session_state.get(sig_key):
        return
    try:
        text, source = files.extract_uploads(items, reader)
    except Exception as exc:
        st.session_state[sig_key] = signature
        st.session_state[sig_key + "_error"] = str(exc)
        return
    st.session_state[sig_key] = signature
    st.session_state[sig_key + "_error"] = ""
    st.session_state[draft_key] = text
    st.session_state[source_key] = source
    st.rerun()


def save_materials(user_id: str) -> None:
    job = files.truncate(current_draft(st.session_state, "job_draft"))
    resume = files.truncate(current_draft(st.session_state, "resume_draft"))
    if not job or not resume:
        st.error("Add the job description and your résumé before saving.")
        return
    db.save_profile(
        user_id,
        job,
        st.session_state.get("job_source") or "Pasted text",
        resume,
        st.session_state.get("resume_source") or "Pasted text",
    )
    st.session_state.upload_nonce = int(st.session_state.get("upload_nonce", 0)) + 1
    st.session_state.job_upload_sig = ()
    st.session_state.resume_upload_sig = ()
    st.session_state.job_upload_sig_error = ""
    st.session_state.resume_upload_sig_error = ""
    st.session_state.just_saved = True
    st.rerun()


def drafts_differ(profile: db.ProfileRecord, state=None) -> bool:
    state = st.session_state if state is None else state
    return current_draft(state, "job_draft") != profile.job_description or current_draft(
        state, "resume_draft"
    ) != profile.resume_text


def persist_complete_drafts(user_id: str, profile: db.ProfileRecord, state=None) -> db.ProfileRecord:
    """Store both materials when Practice opens, including text that was not explicitly saved."""
    state = st.session_state if state is None else state
    job = files.truncate(current_draft(state, "job_draft"))
    resume = files.truncate(current_draft(state, "resume_draft"))
    if not job or not resume:
        return profile
    if job == profile.job_description and resume == profile.resume_text:
        return profile
    saved = db.save_profile(
        user_id,
        job,
        state.get("job_source") or "Pasted text",
        resume,
        state.get("resume_source") or "Pasted text",
    )
    state["draft_marker"] = user_id + ":" + saved.updated_at.isoformat()
    state["job_text"] = job
    state["resume_text"] = resume
    return saved


def render_practice(user: db.UserRecord, profile: db.ProfileRecord) -> None:
    if drafts_differ(profile):
        st.info("Materials still has an unfinished edit. This interview uses the last saved copy.")
    interview = db.latest_interview(user.id)
    if interview is None:
        render_start(user, profile)
        return
    if interview.status == "completed" or st.session_state.get("interview_saved_id") == interview.id:
        st.session_state.confirm_restart = False
        st.success("Your interview is saved.")
        turns = db.list_turns(interview.id)
        if turns:
            render_summary(turns)
        render_start(user, profile)
        return
    render_active(interview)


def render_start(user: db.UserRecord, profile: db.ProfileRecord) -> None:
    st.subheader("A conversation, not a quiz")
    st.write(
        "She introduces herself, starts with the usual easy questions, "
        "then asks about what this role actually depends on. You answer out loud."
    )
    if not config.xai_api_key():
        st.error(str(grok_client.GrokNotConfigured()))
        return
    if st.button("Begin interview", type="primary"):
        try:
            with st.spinner("Preparing your interviewer…"):
                script = grok_client.generate_questions(
                    profile.job_description,
                    profile.resume_text,
                    cache_key=user.id,
                )
            db.create_interview(
                user.id,
                profile.job_description,
                profile.resume_text,
                list(script.questions),
                interviewer_name=script.interviewer_name,
                interviewer_title=script.interviewer_title,
                introduction=script.introduction,
                role_name=script.role_name or prompts.interview_name(profile.job_description),
            )
        except grok_client.GrokError as exc:
            st.error(str(exc))
            return
        st.rerun()


def render_summary(turns: list[db.TurnRecord]) -> None:
    st.subheader("Last conversation")
    for turn in turns:
        st.markdown(f"**{turn.question_text}**")
        st.caption("What you said")
        st.write(turn.transcript or "Nothing was captured.")
        st.caption("How an interviewer hopes to hear it")
        st.write(turn.model_answer)
        st.caption("Keep this, then sharpen one thing")
        st.write(turn.guidance)
        st.divider()


def render_active(interview: db.InterviewRecord) -> None:
    questions = interview.questions
    if not questions:
        st.error("This interview has no questions. Start a new one.")
        if st.button("End this interview", key=f"end_empty_{interview.id}"):
            finish_interview(interview.id)
        return
    if interview.current_index >= len(questions):
        db.set_interview_status(interview.id, "completed")
        st.rerun()

    index = interview.current_index
    question = questions[index]
    question_card(interview, index, question)
    if st.button("End this interview", key=f"end_{interview.id}"):
        st.session_state.confirm_restart = interview.id
    if st.session_state.get("confirm_restart") == interview.id:
        if st.button("Yes, end it", key=f"yes_end_{interview.id}"):
            finish_interview(interview.id)

    earlier = [turn for turn in db.list_turns(interview.id) if turn.question_index < index]
    if earlier:
        with st.expander("Earlier questions"):
            for turn in earlier:
                st.markdown(f"**{turn.question_text}**")
                st.write(turn.model_answer)

    turn = db.get_turn(interview.id, index)
    if turn is None:
        capture_answer(interview, index, question)
        return
    show_feedback(interview, turn, index, len(questions))


def spoken_line(interview: db.InterviewRecord, index: int, question: str) -> str:
    bridges = interview.bridges or {}
    if index == 0:
        lead = interview.introduction
    else:
        lead = bridges.get(index, "")
    if lead:
        return f"{lead} {question}".strip()
    return question


def question_card(interview: db.InterviewRecord, index: int, question: str) -> None:
    bridges = interview.bridges or {}
    aside = interview.introduction if index == 0 else bridges.get(index, "")
    who = ""
    if interview.interviewer_name:
        who = (
            "<div class='who'>"
            f"<div class='name'>{html.escape(interview.interviewer_name)}</div>"
            f"<div class='role'>{html.escape(interview.interviewer_title)}</div>"
            "</div>"
        )
    aside_html = f"<p class='aside'>{html.escape(aside)}</p>" if aside else ""
    st.markdown(
        "<div class='studio'>"
        f"{who}"
        f"{aside_html}"
        f"<p class='ask'>{html.escape(question)}</p>"
        f"<div class='count'>{index + 1} of {len(interview.questions)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def capture_answer(interview: db.InterviewRecord, index: int, question: str) -> None:
    pending_key = f"pending_answer_{interview.id}_{index}"
    attempt = int(st.session_state.get(f"attempt_{interview.id}_{index}", 0))
    pending = st.session_state.get(pending_key)
    if pending is None:
        token = f"{interview.id}-{index}-{attempt}"
        result = interview_voice(spoken_line(interview, index, question), token, MAX_ANSWER_SECONDS)
        if result and result.get("status") == "done":
            st.session_state[pending_key] = {
                "transcript": (result.get("transcript") or "").strip(),
                "reason": result.get("reason") or "manual",
            }
            st.rerun()
        with st.expander("Microphone unavailable? Type your answer"):
            typed = st.text_area(
                "Typed answer",
                key=f"typed_{token}",
                height=120,
                label_visibility="collapsed",
                placeholder="Type the answer you would say out loud",
            )
            if st.button("Submit typed answer", key=f"typed_btn_{token}"):
                st.session_state[pending_key] = {
                    "transcript": (typed or "").strip(),
                    "reason": "typed",
                }
                st.rerun()
        return

    st.markdown("**What you said**")
    st.write(pending["transcript"] or "Nothing was captured.")
    try:
        with st.spinner("Shaping a stronger answer…"):
            prior = [
                (turn.question_text, turn.transcript)
                for turn in db.list_turns(interview.id)
                if turn.question_index < index
            ]
            answer, guidance, bridge = grok_client.coach_answer(
                job_description=interview.job_description,
                resume_text=interview.resume_text,
                question=question,
                transcript=pending["transcript"],
                prior=prior,
                cache_key=interview.id,
            )
        db.save_turn(
            interview.id,
            index,
            question,
            pending["transcript"],
            answer,
            guidance,
            pending.get("reason") or "",
        )
        if index + 1 < len(interview.questions):
            db.set_bridge(interview.id, index + 1, bridge)
    except grok_client.GrokError as exc:
        st.error(str(exc))
        if st.button("Try Grok again"):
            st.rerun()
        if st.button("Record again"):
            discard_attempt(interview.id, index, attempt)
        return
    del st.session_state[pending_key]
    st.rerun()


def show_feedback(interview: db.InterviewRecord, turn: db.TurnRecord, index: int, total: int) -> None:
    st.markdown("**What you said**")
    st.write(turn.transcript or "Nothing was captured.")
    if turn.stop_reason == "time":
        st.caption("Recording stopped at 3 minutes.")
    elif turn.stop_reason == "silence":
        st.caption("Recording stopped after a pause.")
    elif turn.stop_reason == "typed":
        st.caption("This answer was typed.")
    st.markdown("**How an interviewer hopes to hear it**")
    st.write(turn.model_answer)
    st.markdown("**Keep this, then sharpen one thing**")
    st.write(turn.guidance)
    left, right = st.columns(2)
    with left:
        if st.button("Answer again"):
            db.delete_turn(interview.id, index)
            discard_attempt(interview.id, index, int(st.session_state.get(f"attempt_{interview.id}_{index}", 0)))
    with right:
        if index + 1 < total:
            if st.button("Next question", type="primary"):
                db.set_current_index(interview.id, index + 1)
                st.rerun()
        elif st.button("Finish interview", type="primary"):
            db.set_interview_status(interview.id, "completed")
            st.rerun()


def finish_interview(interview_id: str) -> None:
    db.set_interview_status(interview_id, "completed")
    st.session_state.confirm_restart = False
    st.session_state.interview_saved_id = interview_id
    st.rerun()


def discard_attempt(interview_id: str, index: int, attempt: int) -> None:
    st.session_state.pop(f"pending_answer_{interview_id}_{index}", None)
    st.session_state[f"attempt_{interview_id}_{index}"] = attempt + 1
    st.rerun()
