"""Streamlit screens for sign-in, materials, and spoken practice."""

from __future__ import annotations

import html
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from interview_app import auth, config, db, files, grok_client, mailer, prompts
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
    "history_limit",
    "job_file_id",
    "resume_file_id",
    "storage_note",
    "materials_restored",
    "materials_repair_checked",
    "practice_choice",
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

    problem = config.cloud_config_problem()
    if problem:
        st.error(problem)
        st.stop()

    if st.session_state.get("logged_out") and st.session_state.get("want_google_logout"):
        nonce = str(st.session_state.get("logout_nonce") or "")
        result = session_bridge(action="clear", nonce=nonce)
        if result and result.get("action") == "clear" and str(result.get("nonce") or "") == nonce:
            st.logout()
        st.info("Signing out…")
        st.stop()

    render_session_cookie()
    consume_verification()
    user = current_user()
    db.set_actor(user.id if user else None)
    if user is None:
        cloud_storage_notice()
        render_login()
        return
    try:
        render_app(user)
    except db.NotOwner:
        st.error("That interview is not on this account.")


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
        .block-container:has(.left-rail) {
            max-width: 1180px;
            padding-top: 1.2rem;
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
            border-radius: 12px;
            padding: 0;
        }
        [data-testid="stFileUploaderDropzone"] {
            padding: 0.2rem 0.55rem !important;
            min-height: 0 !important;
        }
        [data-testid="stFileUploaderDropzoneInstructions"] {
            display: none !important;
        }
        [data-testid="stSidebar"],
        [data-testid="stExpandSidebarButton"],
        [data-testid="stSidebarCollapseButton"] {
            display: none !important;
        }
        [data-testid="stHorizontalBlock"]:has(.left-rail) {
            align-items: stretch;
            gap: 0.5rem;
        }
        .left-rail { display: none; }
        [data-testid="stColumn"]:has(.left-rail) {
            position: sticky;
            top: 0;
            align-self: flex-start;
            height: calc(100vh - 1.4rem);
            overflow: auto;
            background: #E5EEE9;
            border: 1px solid #D3DDD7;
            border-radius: 18px;
            padding: 0 0.85rem 1rem;
        }
        [data-testid="stColumn"]:has(.left-rail) :is([data-testid="stElementContainer"], [data-testid="element-container"], .stElementContainer):has(.brand) {
            position: sticky !important;
            top: 0;
            z-index: 30;
            background: #E5EEE9;
            margin-left: -0.85rem;
            margin-right: -0.85rem;
            padding: 0.85rem 0.85rem 0.55rem;
        }
        [data-testid="stColumn"]:has(.left-rail) [data-testid="stVerticalBlock"] {
            display: flex;
            flex-direction: column;
            min-height: 100%;
        }
        [data-testid="stColumn"]:has(.left-rail) [data-testid="stVerticalBlock"] > div:has(.sidebar-history-anchor) {
            margin-top: auto;
        }
        [data-testid="stColumn"]:has(.left-rail) .stButton > button {
            background: transparent;
            color: var(--ink);
            border: 1px solid transparent;
            border-radius: 10px;
            text-align: left;
            justify-content: flex-start;
            font-weight: 600;
            box-shadow: none;
        }
        [data-testid="stColumn"]:has(.left-rail) .stButton > button[kind="primary"],
        [data-testid="stColumn"]:has(.left-rail) .stButton > button[data-testid="stBaseButton-primary"] {
            background: var(--forest);
            color: #F6F3EC;
            border-color: var(--forest);
        }
        .brand { display: flex; gap: 0.75rem; align-items: center; margin: 0 0 0.85rem; }
        .brand .mark { width: 42px; height: 42px; flex: none; }
        .brand-name { font-size: 1.05rem; font-weight: 700; letter-spacing: -0.02em; color: var(--ink); line-height: 1.15; }
        .brand-tag { color: var(--brass); font-size: 0.92rem; font-weight: 600; margin-top: 0.12rem; }
        .account-name { font-weight: 650; color: var(--ink); margin-top: 0.8rem; }
        .account-email { color: #24312C; font-size: 0.92rem; margin-bottom: 0.85rem; }
        .files { margin: 0.2rem 0 0.6rem; }
        .file-label {
            color: var(--forest);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin-top: 0.85rem;
        }
        .file {
            color: #14221E;
            font-weight: 650;
            font-size: 0.95rem;
            line-height: 1.35;
            padding: 0.15rem 0 0.35rem;
            word-break: break-word;
        }
        .history-title {
            color: var(--forest);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin: 0.2rem 0 0.45rem;
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
        .studio .aside { color: #2E3330; font-size: 1.02rem; line-height: 1.5; margin: 0.4rem 0 0.2rem; }
        .studio .brief-line { font-size: 1.08rem; line-height: 1.45; margin: 0 0 0.55rem; color: var(--ink); }
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
        user_id = auth.authenticated_user_id(token, config.auth_cookie_secret()) if token else None
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
    token = read_cookie() or str(st.session_state.get("pending_cookie") or "")
    if token:
        auth.revoke_session_token(token, config.auth_cookie_secret())
    st.session_state.logged_out = True
    st.session_state.want_google_logout = google_identity() is not None
    st.session_state.logout_nonce = secrets.token_hex(8)
    st.session_state.auth_user_id = None
    st.session_state.pending_cookie = None
    clear_user_views()
    st.rerun()


def query_value(name: str) -> str:
    try:
        value = st.query_params.get(name, "")
    except Exception:
        return ""
    if isinstance(value, list):
        return str(value[0] if value else "")
    return str(value or "")


def consume_verification() -> None:
    token = query_value("verify")
    if not token:
        return
    if auth.confirm_verification(token):
        st.success("Email confirmed.")
    else:
        st.warning("That confirmation link has expired.")
    try:
        del st.query_params["verify"]
    except Exception:
        pass


def render_login() -> None:
    st.markdown(BRAND, unsafe_allow_html=True)
    st.caption("Your résumé and the role stay with your account.")
    render_reset_link()
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
    render_forgot_password()
    render_about()
    render_contact("sign-in")
    if not submitted:
        return
    try:
        if mode == "Create account":
            if password != confirm:
                st.error("Those passwords do not match.")
                return
            user = auth.register_user(name, email, password)
            try:
                auth.send_verification(user)
            except Exception:
                st.caption("The account is ready. The confirmation email could not be sent.")
        else:
            user = auth.login_user(email, password)
    except auth.AuthError as exc:
        st.error(str(exc))
        return
    st.session_state.logged_out = False
    st.session_state.want_google_logout = False
    st.session_state.auth_user_id = user.id
    st.session_state.pending_cookie = auth.open_session(user.id, config.auth_cookie_secret())
    st.rerun()


def render_reset_link() -> None:
    token = query_value("reset")
    if not token:
        return
    st.subheader("Choose a new password")
    with st.form("reset-password"):
        password = st.text_input("New password", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Update password")
    if submitted:
        if password != confirm:
            st.error("Those passwords do not match.")
        else:
            try:
                auth.reset_password(token, password)
            except auth.AuthError as exc:
                st.error(str(exc))
            else:
                try:
                    del st.query_params["reset"]
                except Exception:
                    pass
                st.success("Password updated. Log in with the new one.")


def render_forgot_password() -> None:
    with st.expander("Forgot password"):
        with st.form("forgot-password"):
            reset_email = st.text_input("Email for a reset link")
            send = st.form_submit_button("Email a reset link")
        if send:
            try:
                auth.request_password_reset(reset_email)
            except auth.AuthError as exc:
                st.error(str(exc))
            except Exception:
                st.error("The email could not be sent. Use Contact us.")
            else:
                st.success("If that email has a password account, a reset link is on its way.")


def render_about() -> None:
    with st.expander("About this app"):
        st.write(
            "Interview Practice is a private rehearsal. You add a job and a résumé, "
            "then speak or type through one interview at a time."
        )


def render_contact(prefix: str) -> None:
    address = config.contact_email()
    with st.expander("Contact us"):
        if address:
            st.markdown(f"[{address}](mailto:{address})")
        with st.form(f"contact-{prefix}"):
            reply = st.text_input("Your email")
            message = st.text_area("Message", height=120)
            send = st.form_submit_button("Send")
        if not send:
            return
        cleaned = (message or "").strip()
        reply_email = (reply or "").strip()
        if not cleaned:
            st.error("Write a message first.")
            return
        if "@" not in reply_email:
            st.error("Add your email so we can reply.")
            return
        try:
            db.save_contact_message(reply_email, cleaned)
            sent = mailer.deliver_contact(reply_email, cleaned)
        except Exception:
            st.error("Your message was saved, but the email could not be sent.")
            return
        if sent:
            st.success("Message sent. We'll reply by email.")
        else:
            st.warning("Your message is saved. No email was sent because mail is not connected.")


def render_app(user: db.UserRecord) -> None:
    profile = db.get_profile(user.id)
    missing = profile is None or not profile.job_description.strip() or not profile.resume_text.strip()
    if missing and st.session_state.get("materials_repair_checked") != user.id:
        repaired = repair_saved_materials(user.id, profile)
        st.session_state["materials_repair_checked"] = user.id
        if _materials_were_restored(profile, repaired):
            st.session_state["materials_restored"] = True
        profile = repaired
    ensure_drafts(user, profile)
    rail, stage = st.columns([1, 1.65], gap="medium")
    with rail:
        st.markdown('<div class="left-rail"></div>', unsafe_allow_html=True)
        render_sidebar(user, profile)
    with stage:
        if st.session_state.pop("just_saved", False):
            st.success("Saved. It will be here the next time you sign in.")
        profile = persist_complete_drafts(user.id, profile)
        interview = current_interview(user.id)
        choice = st.session_state.get("practice_choice")
        if interview is not None and choice not in {"continue", "new", "new-profile"}:
            st.title("Practice")
            render_session_choices(profile, interview)
            return
        if choice in {"new", "new-profile"}:
            st.title(practice_heading(profile, None))
            if choice == "new-profile":
                st.write("Update the job description and résumé on the left, then start.")
            if not profile_ready(profile):
                st.write("Add a job description and your résumé on the left, then begin.")
                return
            render_start(user, profile)
            return
        st.title(practice_heading(profile, heading_interview(interview)))
        if choice == "continue" and interview is not None and interview.status == "active":
            render_practice(user, profile, interview)
            return
        if not profile_ready(profile):
            st.write("Add a job description and your résumé on the left, then begin.")
            return
        render_practice(user, profile, interview)


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


def render_session_choices(profile: db.ProfileRecord | None, interview: db.InterviewRecord) -> None:
    st.subheader(interview_history_label(interview))
    if st.button("Continue previous interview", type="primary", use_container_width=True):
        st.session_state.practice_choice = "continue"
        st.session_state.selected_interview_id = interview.id
        st.rerun()
    if profile_ready(profile) and st.button(
        "Start a new interview with this job and résumé",
        use_container_width=True,
    ):
        st.session_state.practice_choice = "new"
        st.session_state.selected_interview_id = None
        st.rerun()
    if st.button("Start a new interview with a different job and résumé", use_container_width=True):
        st.session_state.practice_choice = "new-profile"
        st.session_state.selected_interview_id = None
        st.rerun()


def ensure_drafts(user: db.UserRecord, profile: db.ProfileRecord | None, state=None) -> None:
    """Keep material text available after the Materials form is closed.

    The text boxes use widget keys. Streamlit removes those keys when Practice
    is showing, so a second copy is kept under a key that is not a widget.
    A blank box must not replace text that is already saved on the account.
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
        state["job_file_id"] = profile.job_file_id if profile else ""
        state["resume_file_id"] = profile.resume_file_id if profile else ""
        return
    if not state.get("job_file_id") and profile and profile.job_file_id:
        state["job_file_id"] = profile.job_file_id
    if not state.get("resume_file_id") and profile and profile.resume_file_id:
        state["resume_file_id"] = profile.resume_file_id
    for widget_key, durable_key, attr, source_key in _DRAFT_FIELDS:
        saved = getattr(profile, attr) if profile else ""
        if not str(state.get(durable_key) or "").strip() and saved.strip():
            state[durable_key] = saved
        if widget_key not in state or (
            not str(state.get(widget_key) or "").strip() and str(state.get(durable_key) or "").strip()
        ):
            state[widget_key] = state.get(durable_key) or ""
        if not str(state.get(source_key) or "").strip() and profile:
            saved_source = getattr(profile, source_key) or ""
            if saved_source:
                state[source_key] = saved_source


def remember_drafts(state) -> None:
    for widget_key, durable_key, _attr, _source_key in _DRAFT_FIELDS:
        if widget_key not in state:
            continue
        typed = state.get(widget_key) or ""
        if typed.strip() or not str(state.get(durable_key) or "").strip():
            state[durable_key] = typed


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


def uploaded_name(source: str, text: str, pasted_label: str) -> str:
    if not (text or "").strip():
        return "Nothing uploaded yet"
    if source and source != "Pasted text":
        return source
    return pasted_label


def interview_history_label(interview: db.InterviewRecord) -> str:
    name = (interview.role_name or "").strip() or prompts.interview_name(interview.job_description)
    if not name or name == "Practice":
        name = "Interview"
    if len(name) > 42:
        name = name[:41].rstrip() + "…"
    if interview.status == "active":
        return f"{name} · in progress"
    created = interview.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    local = created.astimezone(ZoneInfo("America/Edmonton"))
    when = local.strftime("%b %d").replace(" 0", " ")
    return f"{name} · {when}"


def current_interview(user_id: str) -> db.InterviewRecord | None:
    chosen = st.session_state.get("selected_interview_id")
    if chosen:
        interview = db.get_interview(str(chosen))
        if interview and interview.user_id == user_id:
            return interview
        st.session_state.selected_interview_id = None
    return db.latest_interview(user_id)


def heading_interview(interview: db.InterviewRecord | None) -> db.InterviewRecord | None:
    if interview is None:
        return None
    selected = st.session_state.get("selected_interview_id")
    if selected and interview.id == selected:
        return interview
    if interview.status == "active":
        return interview
    return None


def render_sidebar(user: db.UserRecord, profile: db.ProfileRecord | None) -> None:
    remember_drafts(st.session_state)
    restore_draft_widgets(st.session_state)
    job_text = current_draft(st.session_state, "job_draft") or (profile.job_description if profile else "")
    resume_text = current_draft(st.session_state, "resume_draft") or (profile.resume_text if profile else "")
    job_source = st.session_state.get("job_source") or (profile.job_source if profile else "")
    resume_source = st.session_state.get("resume_source") or (profile.resume_source if profile else "")
    st.markdown(BRAND, unsafe_allow_html=True)
    st.markdown(
        "<div class='account-name'>"
        + html.escape(user.name or user.email)
        + "</div><div class='account-email'>"
        + html.escape(user.email)
        + "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div class='files'>"
        "<div class='file-label'>Job description</div>"
        f"<div class='file'>{html.escape(uploaded_name(job_source, job_text, 'Pasted job description'))}</div>"
        "<div class='file-label'>Résumé</div>"
        f"<div class='file'>{html.escape(uploaded_name(resume_source, resume_text, 'Pasted résumé'))}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    offer_download(user.id, str(st.session_state.get("job_file_id") or ""), "Download job file", f"dl_job_{user.id}")
    offer_download(
        user.id,
        str(st.session_state.get("resume_file_id") or ""),
        "Download résumé file",
        f"dl_resume_{user.id}",
    )
    render_sidebar_editor(
        user,
        upload_label="Update job description",
        paste_label="Job description text",
        draft_key="job_draft",
        source_key="job_source",
        sig_key="job_upload_sig",
        upload_key=f"job_files_{user.id}_{st.session_state.get('upload_nonce', 0)}",
    )
    render_sidebar_editor(
        user,
        upload_label="Update résumé",
        paste_label="Résumé text",
        draft_key="resume_draft",
        source_key="resume_source",
        sig_key="resume_upload_sig",
        upload_key=f"resume_files_{user.id}_{st.session_state.get('upload_nonce', 0)}",
    )
    if st.session_state.pop("materials_restored", False):
        st.caption("Your job description and résumé are back on this account.")
    note = st.session_state.get("storage_note")
    if note:
        st.caption(note)
    render_account(user)
    render_contact(f"sidebar-{user.id}")
    render_change_password(user)
    if st.button("Log out", type="secondary", use_container_width=True):
        request_logout()
    cloud_storage_notice()
    if config.uses_local_sqlite() and not config.on_streamlit_cloud():
        st.caption("Saving to a local database file. Set DATABASE_URL to use Postgres.")
    st.markdown("<div class='sidebar-history-anchor'></div>", unsafe_allow_html=True)
    st.markdown("<div class='history-title'>Past interviews</div>", unsafe_allow_html=True)
    render_interview_history(user.id)


def render_sidebar_editor(
    user: db.UserRecord,
    *,
    upload_label: str,
    paste_label: str,
    draft_key: str,
    source_key: str,
    sig_key: str,
    upload_key: str,
) -> None:
    uploads = st.file_uploader(
        upload_label,
        accept_multiple_files=True,
        key=upload_key,
        help="10MB max file size",
    )
    apply_upload(uploads, sig_key, draft_key, source_key, image_reader_for(user.id), user.id)
    error = st.session_state.get(sig_key + "_error")
    if error:
        st.error(error)
    with st.expander("Edit the text"):
        st.text_area(
            paste_label,
            key=draft_key,
            height=140,
            label_visibility="collapsed",
            on_change=autosave_materials,
            args=(user.id,),
        )


def render_interview_history(user_id: str) -> None:
    shown = int(st.session_state.get("history_limit", 20))
    interviews = db.list_interviews(user_id, limit=shown)
    total = db.count_interviews(user_id)
    if not interviews:
        st.caption("No interviews yet.")
        return
    selected = st.session_state.get("selected_interview_id")
    latest = interviews[0]
    for interview in interviews:
        active = interview.id == selected or (not selected and interview.id == latest.id and interview.status == "active")
        if st.button(
            interview_history_label(interview),
            key=f"history_{interview.id}",
            type="primary" if active else "secondary",
            use_container_width=True,
        ):
            st.session_state.selected_interview_id = interview.id
            st.session_state.practice_choice = "continue"
            st.session_state.confirm_restart = False
            st.rerun()
    if total > len(interviews):
        if st.button(f"Earlier interviews ({total - len(interviews)} more)", key="earlier_interviews"):
            st.session_state.history_limit = shown + 20
            st.rerun()


def offer_download(user_id: str, file_id: str, label: str, key: str) -> None:
    found = db.read_file(file_id, user_id) if file_id else None
    if not found:
        return
    name, data = found
    st.download_button(label, data=data, file_name=name, key=key)


def render_change_password(user: db.UserRecord) -> None:
    if not user.password_hash:
        return
    with st.expander("Change password"):
        with st.form(f"change-password-{user.id}"):
            current = st.text_input("Current password", type="password")
            new_password = st.text_input("New password", type="password")
            change = st.form_submit_button("Change password")
        if not change:
            return
        try:
            auth.change_password(user.id, current, new_password)
        except auth.AuthError as exc:
            st.error(str(exc))
            return
        st.session_state.pending_cookie = auth.open_session(user.id, config.auth_cookie_secret())
        st.session_state.password_updated = True
        st.rerun()


def render_account(user: db.UserRecord) -> None:
    if st.session_state.pop("password_updated", False):
        st.success("Password updated. Other sessions were signed out.")
    used, limit, calls, call_limit = db.usage_today(user.id)
    st.caption(f"{used} of {limit} interviews started today. {calls} of {call_limit} interviewer replies.")
    if mailer.configured() and user.password_hash and user.email_verified_at is None:
        st.caption("This email is not confirmed yet.")
        if st.button("Send confirmation email", key="resend_verify"):
            try:
                auth.send_verification(user)
                st.success("Confirmation email sent.")
            except Exception:
                st.error("The email could not be sent.")
    with st.expander("Account"):
        export = db.export_account(user.id)
        st.download_button(
            "Download my data",
            data=json.dumps(export, indent=2).encode("utf-8"),
            file_name="interview-practice.json",
            mime="application/json",
            key=f"export_{user.id}",
        )
        st.caption("Deleting the account removes the résumé, interviews, and stored files.")
        confirm = st.text_input("Type your email to delete the account", key=f"delete_email_{user.id}")
        if st.button("Delete account", key=f"delete_{user.id}"):
            if confirm.strip().lower() != user.email:
                st.error("Type the account email to confirm.")
            else:
                db.delete_account(user.id)
                request_logout()
        if config.is_admin(user.email):
            st.markdown("**Messages**")
            messages = db.recent_contact_messages()
            if not messages:
                st.caption("No messages yet.")
            for created, reply_email, message in messages:
                when = created.strftime("%b %d %H:%M") if created else ""
                st.caption(f"{when} · {reply_email or 'no email'}")
                st.write(message)
            st.markdown("**Recent problems**")
            events = db.recent_events("error", limit=20)
            if not events:
                st.caption("No recorded problems.")
            for created, owner, message in events:
                when = created.strftime("%b %d %H:%M") if created else ""
                st.caption(f"{when} · {owner or 'system'} · {message or 'error'}")


def image_reader_for(user_id: str):
    def read(data: bytes, mime: str) -> str:
        return grok_client.extract_document_text(data, mime, cache_key=user_id, user_id=user_id)

    return read


def apply_upload(uploads, sig_key: str, draft_key: str, source_key: str, reader, user_id: str) -> None:
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
    kind = "job" if "job" in sig_key else "resume"
    file_id = ""
    for item in items:
        saved_id = db.store_file(user_id, kind, Path(getattr(item, "name", "upload")).name, item.getvalue())
        if saved_id:
            file_id = saved_id
    st.session_state[sig_key] = signature
    st.session_state[sig_key + "_error"] = ""
    st.session_state[draft_key] = text
    st.session_state[source_key] = source
    if file_id:
        st.session_state[kind + "_file_id"] = file_id
        st.session_state["storage_note"] = ""
    else:
        st.session_state["storage_note"] = (
            "The text was saved. The original file was not kept because stored files are at the 25 MB limit."
        )
    autosave_materials(user_id, clear_uploads=True)
    st.rerun()


def _kept_material(state, widget_key: str, durable_key: str, saved: str) -> str:
    """Keep saved text when the editor is blank because the page did not load it."""
    saved = saved or ""
    typed = files.truncate(state.get(widget_key) or "") if widget_key in state else ""
    if typed.strip():
        state[durable_key] = typed
        return typed
    durable = files.truncate(state.get(durable_key) or "") if durable_key in state else ""
    chosen = durable if durable.strip() else saved
    if chosen.strip():
        state[widget_key] = chosen
        state[durable_key] = chosen
    return chosen


def _kept_label(state, source_key: str, saved_source: str, text: str, saved_text: str) -> str:
    source = str(state.get(source_key) or "")
    if text == (saved_text or ""):
        return saved_source or source
    return source or saved_source


def _stamp(value) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _text_from_stored_file(user_id: str, file_id: str) -> str:
    found = db.read_file(file_id, user_id)
    if not found:
        return ""
    name, data = found
    try:
        return files.truncate(files.extract_named_bytes(name, data, None))
    except Exception:
        return ""


def _recover_side(
    user_id: str,
    text: str,
    source: str,
    file_id: str,
    interview: db.InterviewRecord | None,
    stored: db.StoredFileInfo | None,
    interview_text: str,
    interview_source: str,
    interview_file_id: str,
) -> tuple[str, str, str]:
    if text.strip():
        return text, source, file_id
    choices: list[tuple[datetime, str, str, str]] = []
    if interview is not None and interview_text.strip():
        choices.append((_stamp(interview.created_at), interview_text, interview_source, interview_file_id))
    if stored is not None:
        extracted = _text_from_stored_file(user_id, stored.id)
        if extracted.strip():
            choices.append((_stamp(stored.created_at), extracted, stored.filename, stored.id))
    if not choices:
        return text, source, file_id
    _when, recovered_text, recovered_source, recovered_file = max(choices, key=lambda item: item[0])
    return recovered_text, recovered_source or source, recovered_file or file_id


def repair_saved_materials(user_id: str, profile: db.ProfileRecord | None) -> db.ProfileRecord | None:
    """Put back a job description or résumé that a blank editor saved over."""
    job = profile.job_description if profile else ""
    resume = profile.resume_text if profile else ""
    if job.strip() and resume.strip():
        return profile
    interview = db.newest_interview_with_materials(user_id)
    job, job_source, job_file_id = _recover_side(
        user_id,
        job,
        profile.job_source if profile else "",
        profile.job_file_id if profile else "",
        interview,
        db.newest_stored_file(user_id, "job"),
        interview.job_description if interview else "",
        interview.job_source if interview else "",
        interview.job_file_id if interview else "",
    )
    resume, resume_source, resume_file_id = _recover_side(
        user_id,
        resume,
        profile.resume_source if profile else "",
        profile.resume_file_id if profile else "",
        interview,
        db.newest_stored_file(user_id, "resume"),
        interview.resume_text if interview else "",
        interview.resume_source if interview else "",
        interview.resume_file_id if interview else "",
    )
    if profile is not None and job == profile.job_description and resume == profile.resume_text:
        return profile
    if not job.strip() and not resume.strip():
        return profile
    return db.save_profile(
        user_id,
        job,
        job_source,
        resume,
        resume_source,
        job_file_id=job_file_id or None,
        resume_file_id=resume_file_id or None,
    )


def _materials_were_restored(before: db.ProfileRecord | None, after: db.ProfileRecord | None) -> bool:
    if after is None:
        return False
    before_job = before.job_description.strip() if before else ""
    before_resume = before.resume_text.strip() if before else ""
    return (not before_job and bool(after.job_description.strip())) or (
        not before_resume and bool(after.resume_text.strip())
    )


def autosave_materials(user_id: str, *, clear_uploads: bool = False, state=None) -> None:
    state = st.session_state if state is None else state
    profile = db.get_profile(user_id)
    job = _kept_material(state, "job_draft", "job_text", profile.job_description if profile else "")
    resume = _kept_material(state, "resume_draft", "resume_text", profile.resume_text if profile else "")
    job_source = _kept_label(state, "job_source", profile.job_source if profile else "", job, profile.job_description if profile else "")
    resume_source = _kept_label(
        state,
        "resume_source",
        profile.resume_source if profile else "",
        resume,
        profile.resume_text if profile else "",
    )
    if not job_source and job:
        job_source = "Pasted text"
    if not resume_source and resume:
        resume_source = "Pasted text"
    if not job.strip() and not resume.strip():
        return
    job_file_id = state.get("job_file_id") or None
    resume_file_id = state.get("resume_file_id") or None
    if job == (profile.job_description if profile else "") and not job_file_id and profile:
        job_file_id = profile.job_file_id or None
    if resume == (profile.resume_text if profile else "") and not resume_file_id and profile:
        resume_file_id = profile.resume_file_id or None
    unchanged = (
        profile is not None
        and job == profile.job_description
        and resume == profile.resume_text
        and job_source == profile.job_source
        and resume_source == profile.resume_source
        and (job_file_id or "") == (profile.job_file_id or "")
        and (resume_file_id or "") == (profile.resume_file_id or "")
    )
    if not unchanged:
        saved = db.save_profile(
            user_id,
            job,
            job_source,
            resume,
            resume_source,
            job_file_id=job_file_id,
            resume_file_id=resume_file_id,
        )
        state["draft_marker"] = user_id + ":" + saved.updated_at.isoformat()
        state["job_text"] = job
        state["resume_text"] = resume
        state["job_draft"] = job
        state["resume_draft"] = resume
        state["job_source"] = job_source
        state["resume_source"] = resume_source
        if job_file_id:
            state["job_file_id"] = job_file_id
        if resume_file_id:
            state["resume_file_id"] = resume_file_id
    if clear_uploads:
        state["upload_nonce"] = int(state.get("upload_nonce", 0)) + 1
        state["job_upload_sig"] = ()
        state["resume_upload_sig"] = ()
        state["job_upload_sig_error"] = ""
        state["resume_upload_sig_error"] = ""


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


def render_practice(
    user: db.UserRecord,
    profile: db.ProfileRecord,
    interview: db.InterviewRecord | None,
) -> None:
    if interview is None:
        render_start(user, profile)
        return
    render_session_files(user.id, interview)
    if interview.status == "active" and st.session_state.get("interview_saved_id") != interview.id:
        render_active(interview)
        return
    st.session_state.confirm_restart = False
    if st.session_state.get("interview_saved_id") == interview.id:
        st.success("Your interview is saved.")
    turns = db.list_turns(interview.id)
    if turns:
        render_summary(turns)
    render_start(user, profile)


def render_session_files(user_id: str, interview: db.InterviewRecord) -> None:
    job = uploaded_name(interview.job_source, interview.job_description, "Pasted job description")
    resume = uploaded_name(interview.resume_source, interview.resume_text, "Pasted résumé")
    st.markdown(
        "<div class='session-files'>"
        "<div class='file-label'>Files for this session</div>"
        f"<div class='file'>{html.escape(job)}</div>"
        f"<div class='file'>{html.escape(resume)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    offer_download(user_id, interview.job_file_id, "Download job file", f"dl_session_job_{interview.id}")
    offer_download(user_id, interview.resume_file_id, "Download résumé file", f"dl_session_resume_{interview.id}")


def render_start(user: db.UserRecord, profile: db.ProfileRecord) -> None:
    st.subheader("A conversation, not a quiz")
    st.write("You have 3 minutes for each answer. You can speak, or type.")
    st.write("First you'll check the microphone, then she'll start with a little small talk.")
    st.write("She starts with a short picture of the role, then the questions.")
    st.write(
        "She introduces herself, then asks about the work, including situations, "
        "remote or hybrid work, and pay. At the end you can ask her questions."
    )
    if not config.xai_api_key():
        st.error(str(grok_client.GrokNotConfigured()))
        return
    used, limit, _calls, _call_limit = db.usage_today(user.id)
    if used >= limit:
        st.info(f"This account has started {limit} interviews today. The allowance resets overnight.")
        return
    if st.button("Begin interview", type="primary"):
        try:
            with st.spinner("Preparing your interviewer…"):
                script = grok_client.generate_questions(
                    profile.job_description,
                    profile.resume_text,
                    cache_key=f"{user.id}:{secrets.token_hex(4)}",
                    user_id=user.id,
                    avoid=db.questions_for_role(user.id, profile.job_description),
                )
            created = db.create_interview(
                user.id,
                profile.job_description,
                profile.resume_text,
                list(script.questions),
                interviewer_name=script.interviewer_name,
                interviewer_title=script.interviewer_title,
                introduction=script.introduction,
                role_name=script.role_name or prompts.interview_name(profile.job_description),
                job_source=profile.job_source,
                resume_source=profile.resume_source,
                role_brief=script.role_brief,
                job_file_id=profile.job_file_id,
                resume_file_id=profile.resume_file_id,
                small_talk=script.small_talk,
            )
            st.session_state.selected_interview_id = created.id
        except db.QuotaExceeded as exc:
            st.error(str(exc))
            return
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
        if turn.model_answer:
            label = "Her answer" if turn.guidance == "candidate-question" else "How an interviewer hopes to hear it"
            st.caption(label)
            st.write(turn.model_answer)
        if turn.guidance and turn.guidance != "candidate-question":
            st.caption("Keep this, then sharpen one thing")
            st.write(turn.guidance)
        st.divider()


def render_active(interview: db.InterviewRecord) -> None:
    if not interview.mic_checked:
        render_mic_check(interview)
        return
    if not interview.chat_done:
        render_small_talk(interview)
        return
    if interview.role_brief and not interview.brief_done:
        render_role_brief(interview)
        return
    questions = interview.questions
    if not questions:
        st.error("This interview has no questions. Start a new one.")
        if st.button("End this interview", key=f"end_empty_{interview.id}"):
            finish_interview(interview.id)
        return
    if interview.current_index >= len(questions):
        render_candidate_questions(interview)
        return

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
                if turn.model_answer:
                    st.write(turn.model_answer)

    turn = db.get_turn(interview.id, index)
    if turn is None:
        capture_answer(interview, index, question)
        return
    show_feedback(interview, turn, index, len(questions))


def render_mic_check(interview: db.InterviewRecord) -> None:
    who = ""
    if interview.interviewer_name:
        who = (
            "<div class='who'>"
            f"<div class='name'>{html.escape(interview.interviewer_name)}</div>"
            f"<div class='role'>{html.escape(interview.interviewer_title)}</div>"
            "</div>"
        )
    st.markdown(
        "<div class='studio'>"
        f"{who}"
        f"<p class='ask'>{html.escape(prompts.MIC_TEST_QUESTION)}</p>"
        "<p class='aside'>This only checks the microphone. It is not an interview question.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    pending_key = f"mic_check_{interview.id}"
    heard = st.session_state.get(pending_key)
    if heard is None:
        result = interview_voice(prompts.MIC_TEST_QUESTION, f"mic-{interview.id}", 45)
        if result and result.get("status") == "done":
            st.session_state[pending_key] = (result.get("transcript") or "").strip()
            st.rerun()
        with st.expander("Type a few words instead"):
            typed = st.text_area(
                "Microphone test",
                key=f"mic_type_{interview.id}",
                height=80,
                label_visibility="collapsed",
                placeholder="Type a few words if you are not using the microphone",
            )
            if st.button("Submit test", key=f"mic_type_btn_{interview.id}"):
                st.session_state[pending_key] = (typed or "").strip()
                st.rerun()
        return
    if prompts.heard_microphone(heard):
        st.success("The microphone is working.")
        st.write(heard)
        if st.button("Continue", type="primary", key=f"mic_ok_{interview.id}"):
            db.mark_mic_checked(interview.id)
            st.rerun()
        return
    st.warning("Nothing came through. Try the microphone again, or type a few words.")
    if st.button("Try the microphone again", key=f"mic_retry_{interview.id}"):
        st.session_state.pop(pending_key, None)
        st.rerun()


def render_small_talk(interview: db.InterviewRecord) -> None:
    if not interview.chat_log:
        opener = interview.small_talk if prompts.acceptable_small_talk(interview.small_talk) else prompts.fresh_small_talk()
        db.start_small_talk(interview.id, opener)
        st.rerun()
    name = interview.interviewer_name or "She"
    for speaker, text in interview.chat_log:
        st.markdown(f"**{name if speaker == 'interviewer' else 'You'}**")
        st.write(text)
    if interview.chat_wrap:
        if st.button("Continue", type="primary", key=f"chat_continue_{interview.id}"):
            db.mark_chat_done(interview.id)
            st.rerun()
        return
    if st.button("Skip", key=f"chat_skip_{interview.id}"):
        db.mark_chat_done(interview.id)
        st.rerun()
    prompt = interview.chat_log[-1][1]
    pending_key = f"chat_{interview.id}_{len(interview.chat_log)}"
    pending = st.session_state.get(pending_key)
    if pending is None:
        result = interview_voice(prompt, pending_key, 90)
        if result and result.get("status") == "done":
            st.session_state[pending_key] = (result.get("transcript") or "").strip()
            st.rerun()
        with st.expander("Type instead"):
            typed = st.text_area(
                "Small talk",
                key=f"typed_{pending_key}",
                height=80,
                label_visibility="collapsed",
                placeholder="Say whatever you would say in the room",
            )
            if st.button("Send", key=f"send_{pending_key}"):
                st.session_state[pending_key] = (typed or "").strip()
                st.rerun()
        return
    history = list(interview.chat_log)
    if prompts.heard_microphone(pending):
        db.append_chat(interview.id, "you", pending)
        history.append(("you", pending))
    else:
        history.append(("you", "[said nothing]"))
    try:
        reply = grok_client.continue_small_talk(
            history=history,
            cache_key=interview.id,
            user_id=interview.user_id,
        )
    except grok_client.GrokError:
        reply = "Glad to hear it."
    db.append_chat(interview.id, "interviewer", reply, wrap=True)
    st.session_state.pop(pending_key, None)
    st.rerun()


def render_role_brief(interview: db.InterviewRecord) -> None:
    spoken = " ".join(line.strip() for line in interview.role_brief.splitlines() if line.strip())
    body = f"<p class='brief-line'>{html.escape(spoken)}</p>"
    who = ""
    if interview.interviewer_name:
        who = (
            "<div class='who'>"
            f"<div class='name'>{html.escape(interview.interviewer_name)}</div>"
            f"<div class='role'>{html.escape(interview.interviewer_title)}</div>"
            "</div>"
        )
    st.markdown(
        "<div class='studio'>"
        f"{who}"
        f"{body}"
        "<p class='aside'>You have 3 minutes for each answer. You can speak, or type. "
        "You'll have time at the end to ask questions.</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    interview_voice(
        spoken,
        f"brief-{interview.id}",
        MAX_ANSWER_SECONDS,
        speak_only=True,
    )
    if st.button("Begin questions", type="primary", key=f"begin_questions_{interview.id}"):
        db.mark_brief_done(interview.id)
        st.rerun()


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
        st.caption("3 minutes. Speak, or type below.")
        token = f"{interview.id}-{index}-{attempt}"
        result = interview_voice(spoken_line(interview, index, question), token, MAX_ANSWER_SECONDS)
        if result and result.get("status") == "done":
            st.session_state[pending_key] = {
                "transcript": (result.get("transcript") or "").strip(),
                "reason": result.get("reason") or "manual",
            }
            st.rerun()
        with st.expander("Type your answer"):
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
                user_id=interview.user_id,
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
        if bridge and index + 1 < len(interview.questions):
            db.set_bridge(interview.id, index + 1, bridge)
    except grok_client.GrokError as exc:
        st.error(str(exc))
        if st.button("Try again"):
            st.rerun()
        if st.button("Record again"):
            discard_attempt(interview.id, index, attempt)
        return
    del st.session_state[pending_key]
    st.rerun()


def show_feedback(interview: db.InterviewRecord, turn: db.TurnRecord, index: int, total: int) -> None:
    st.markdown("**What you said**")
    st.write(turn.transcript or "Nothing was captured.")
    if prompts.is_non_answer(turn.transcript):
        st.caption("You can take this one again whenever you want. Here's a way through it.")
    elif turn.stop_reason == "time":
        st.caption("Recording stopped at 3 minutes.")
    elif turn.stop_reason == "silence":
        st.caption("Recording stopped after a pause.")
    elif turn.stop_reason == "typed":
        st.caption("This answer was typed.")
    st.markdown("**How an interviewer hopes to hear it**")
    st.write(
        " ".join((turn.model_answer or "").split())
        or "Start with the point in one sentence, then one example of what you did and how it turned out."
    )
    st.markdown("**Keep this, then sharpen one thing**")
    st.write(prompts.feedback_text(turn.transcript, turn.guidance))
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
        elif st.button("Your questions", type="primary"):
            db.set_current_index(interview.id, total)
            st.rerun()


def render_candidate_questions(interview: db.InterviewRecord) -> None:
    index = max(interview.current_index, len(interview.questions))
    if interview.current_index != index:
        db.set_current_index(interview.id, index)
    prompt = prompts.CANDIDATE_OPENING if index == len(interview.questions) else "What else would you like to ask me?"
    st.markdown(
        "<div class='studio'>"
        f"<p class='ask'>{html.escape(prompt)}</p>"
        "<div class='count'>Your questions</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    turn = db.get_turn(interview.id, index)
    if turn is None:
        capture_candidate_question(interview, index, prompt)
        return
    st.markdown("**What you asked**")
    st.write(turn.transcript or "Nothing was captured.")
    st.markdown(f"**{html.escape(interview.interviewer_name or 'She')}**")
    st.write(turn.model_answer)
    left, right = st.columns(2)
    with left:
        if st.button("Ask another", key=f"ask_another_{interview.id}_{index}"):
            db.set_current_index(interview.id, index + 1)
            st.rerun()
    with right:
        if st.button("End this interview", key=f"end_questions_{interview.id}", type="primary"):
            finish_interview(interview.id)


def capture_candidate_question(interview: db.InterviewRecord, index: int, prompt: str) -> None:
    pending_key = f"pending_answer_{interview.id}_{index}"
    attempt = int(st.session_state.get(f"attempt_{interview.id}_{index}", 0))
    pending = st.session_state.get(pending_key)
    if pending is None:
        st.caption("3 minutes. Speak, or type below.")
        token = f"{interview.id}-{index}-{attempt}"
        result = interview_voice(prompt, token, MAX_ANSWER_SECONDS)
        if result and result.get("status") == "done":
            st.session_state[pending_key] = {
                "transcript": (result.get("transcript") or "").strip(),
                "reason": result.get("reason") or "manual",
            }
            st.rerun()
        with st.expander("Type your question"):
            typed = st.text_area(
                "Typed question",
                key=f"typed_{token}",
                height=120,
                label_visibility="collapsed",
                placeholder="Type the question you would ask",
            )
            if st.button("Submit typed question", key=f"typed_btn_{token}"):
                st.session_state[pending_key] = {
                    "transcript": (typed or "").strip(),
                    "reason": "typed",
                }
                st.rerun()
        return
    if prompts.is_non_answer(pending["transcript"]):
        discard_attempt(interview.id, index, attempt)
        return
    try:
        with st.spinner("She is answering…"):
            reply = grok_client.answer_candidate_question(
                job_description=interview.job_description,
                resume_text=interview.resume_text,
                question=pending["transcript"],
                interviewer_name=interview.interviewer_name,
                interviewer_title=interview.interviewer_title,
                cache_key=interview.id,
                user_id=interview.user_id,
            )
        db.save_turn(
            interview.id,
            index,
            prompt,
            pending["transcript"],
            reply,
            "candidate-question",
            pending.get("reason") or "",
        )
    except grok_client.GrokError as exc:
        st.error(str(exc))
        if st.button("Try again", key=f"retry_ask_{interview.id}_{index}"):
            st.rerun()
        return
    st.session_state.pop(pending_key, None)
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
