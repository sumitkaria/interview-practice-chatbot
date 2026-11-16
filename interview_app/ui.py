"""Streamlit screens for sign-in, materials, and spoken practice."""

from __future__ import annotations

import html
import secrets

import streamlit as st

from interview_app import auth, config, db, files, grok_client
from interview_app.components import interview_voice, session_bridge

MAX_ANSWER_SECONDS = 180
_VIEW_PREFIXES = ("pending_answer_", "attempt_", "typed_")
_VIEW_KEYS = {
    "draft_marker",
    "job_draft",
    "resume_draft",
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


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .question-card {
            background: rgba(127, 127, 127, 0.10);
            border-radius: 12px;
            padding: 0.9rem 1.1rem 0.15rem;
            margin: 0.2rem 0 0.8rem;
        }
        .question-kicker {
            font-size: 0.8rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            opacity: 0.7;
            margin-bottom: 0.35rem;
        }
        .question-card p {
            font-size: 1.28rem;
            line-height: 1.45;
            margin-bottom: 0.85rem;
        }
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
    st.title("Interview Practice Assistant")
    st.caption("Sign in to keep your résumé and job description, then practice out loud.")
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
    render_sidebar(user, profile)
    st.title("Interview Practice Assistant")
    if st.session_state.pop("just_saved", False):
        st.success("Saved. This stays with your account the next time you sign in.")
    ready = profile_ready(profile)
    if not ready:
        st.caption("Add the job and your background. They are saved to your account.")
        render_materials(user, profile)
        return
    if "section" not in st.session_state:
        st.session_state.section = "Practice"
    section = st.radio(
        "Section",
        ["Practice", "Materials"],
        horizontal=True,
        label_visibility="collapsed",
        key="section",
    )
    if section == "Materials":
        render_materials(user, profile)
    else:
        render_practice(user, profile)


def profile_ready(profile: db.ProfileRecord | None) -> bool:
    return bool(profile and profile.job_description.strip() and profile.resume_text.strip())


def ensure_drafts(user: db.UserRecord, profile: db.ProfileRecord | None) -> None:
    marker = user.id + ":" + (profile.updated_at.isoformat() if profile else "new")
    if st.session_state.get("draft_marker") == marker:
        return
    st.session_state.draft_marker = marker
    st.session_state.job_draft = profile.job_description if profile else ""
    st.session_state.resume_draft = profile.resume_text if profile else ""
    st.session_state.job_source = profile.job_source if profile else ""
    st.session_state.resume_source = profile.resume_source if profile else ""


def render_sidebar(user: db.UserRecord, profile: db.ProfileRecord | None) -> None:
    with st.sidebar:
        st.markdown("**Interview Practice**")
        st.write(user.name or user.email)
        st.caption(user.email)
        if st.button("Log out", use_container_width=True):
            request_logout()
        if profile_ready(profile):
            st.caption("Job description: " + (profile.job_source or "Saved"))
            st.caption("Background: " + (profile.resume_source or "Saved"))
        cloud_storage_notice()
        if config.uses_local_sqlite() and not config.on_streamlit_cloud():
            st.caption("Saving to a local database file. Set DATABASE_URL to use Postgres.")


def render_materials(user: db.UserRecord, profile: db.ProfileRecord | None) -> None:
    nonce = st.session_state.get("upload_nonce", 0)
    reader = image_reader_for(user.id)
    render_material_editor(
        title="Job description",
        upload_label="Upload a job description",
        paste_label="Or paste the job description",
        draft_key="job_draft",
        source_key="job_source",
        sig_key="job_upload_sig",
        upload_key=f"job_files_{user.id}_{nonce}",
        reader=reader,
    )
    render_material_editor(
        title="Résumé or professional background",
        upload_label="Upload a résumé or background",
        paste_label="Or paste your résumé or background",
        draft_key="resume_draft",
        source_key="resume_source",
        sig_key="resume_upload_sig",
        upload_key=f"resume_files_{user.id}_{nonce}",
        reader=reader,
    )
    st.caption("PDF, Word (.docx), text, Markdown, RTF, HTML, CSV, PNG, or JPG. Older .doc files need to be saved as .docx.")
    if st.button("Save materials", type="primary", use_container_width=True):
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
        type=files.UPLOAD_TYPES,
        accept_multiple_files=True,
        key=upload_key,
        help="You can upload more than one file. Text is combined in the box below, where you can edit it.",
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
    job = files.truncate(st.session_state.get("job_draft", ""))
    resume = files.truncate(st.session_state.get("resume_draft", ""))
    if not job or not resume:
        st.error("Add both a job description and your background before saving.")
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


def drafts_differ(profile: db.ProfileRecord) -> bool:
    return (
        (st.session_state.get("job_draft") or "") != profile.job_description
        or (st.session_state.get("resume_draft") or "") != profile.resume_text
    )


def render_practice(user: db.UserRecord, profile: db.ProfileRecord) -> None:
    if drafts_differ(profile):
        st.info("You have unsaved edits in Materials. This interview uses the last saved copy.")
    interview = db.latest_interview(user.id)
    if interview is None:
        render_start(user, profile)
        return
    if interview.status == "completed":
        turns = db.list_turns(interview.id)
        if turns:
            render_summary(turns)
        render_start(user, profile)
        return
    render_active(interview)


def render_start(user: db.UserRecord, profile: db.ProfileRecord) -> None:
    st.subheader("Start a practice interview")
    st.write(
        "Grok writes questions from your saved background and the job. "
        "Each question is shown here and read aloud. Recording starts after the question, "
        "the transcript appears while you speak, and each answer stops at 3 minutes."
    )
    if not config.xai_api_key():
        st.error(str(grok_client.GrokNotConfigured()))
        return
    st.caption(f"Model: {config.grok_model()} · reasoning: {config.grok_effort()}")
    if st.button("Generate questions", type="primary"):
        try:
            with st.spinner("Writing interview questions…"):
                questions = grok_client.generate_questions(
                    profile.job_description,
                    profile.resume_text,
                    cache_key=user.id,
                )
            db.create_interview(
                user.id,
                profile.job_description,
                profile.resume_text,
                questions,
            )
        except grok_client.GrokError as exc:
            st.error(str(exc))
            return
        st.rerun()


def render_summary(turns: list[db.TurnRecord]) -> None:
    st.subheader("Last interview")
    for turn in turns:
        st.markdown(f"**{turn.question_text}**")
        st.caption("What you said")
        st.write(turn.transcript or "Nothing was captured.")
        st.caption("A stronger way to say it")
        st.write(turn.model_answer)
        st.caption("How to handle it")
        st.write(turn.guidance)
        st.divider()


def render_active(interview: db.InterviewRecord) -> None:
    questions = interview.questions
    if not questions:
        st.error("This interview has no questions. Start a new one.")
        if st.button("End this interview"):
            db.set_interview_status(interview.id, "completed")
            st.rerun()
        return
    if interview.current_index >= len(questions):
        db.set_interview_status(interview.id, "completed")
        st.rerun()

    index = interview.current_index
    question = questions[index]
    st.caption("These questions use the materials saved when this interview started.")
    question_card(index, len(questions), question)
    if st.button("End this interview"):
        st.session_state.confirm_restart = True
    if st.session_state.get("confirm_restart"):
        st.warning("Ending keeps the answers you already finished and leaves your saved materials in place.")
        if st.button("Yes, end it"):
            db.set_interview_status(interview.id, "completed")
            st.session_state.confirm_restart = False
            st.rerun()

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


def question_card(index: int, total: int, question: str) -> None:
    st.markdown(
        "<div class='question-card'>"
        f"<div class='question-kicker'>Question {index + 1} of {total}</div>"
        f"<p>{html.escape(question)}</p></div>",
        unsafe_allow_html=True,
    )


def capture_answer(interview: db.InterviewRecord, index: int, question: str) -> None:
    pending_key = f"pending_answer_{interview.id}_{index}"
    attempt = int(st.session_state.get(f"attempt_{interview.id}_{index}", 0))
    pending = st.session_state.get(pending_key)
    if pending is None:
        st.caption(
            "The question is read aloud, then recording starts. Words appear as you speak. "
            "Chrome and Edge work best. Recording stops when you pause, when you choose Done speaking, or at 3 minutes."
        )
        token = f"{interview.id}-{index}-{attempt}"
        result = interview_voice(question, token, MAX_ANSWER_SECONDS)
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
        with st.spinner("Writing a model answer with Grok…"):
            prior = [
                (turn.question_text, turn.transcript)
                for turn in db.list_turns(interview.id)
                if turn.question_index < index
            ]
            answer, guidance = grok_client.coach_answer(
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
    st.markdown("**A stronger way to say it**")
    st.write(turn.model_answer)
    st.markdown("**How to handle this question**")
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


def discard_attempt(interview_id: str, index: int, attempt: int) -> None:
    st.session_state.pop(f"pending_answer_{interview_id}_{index}", None)
    st.session_state[f"attempt_{interview_id}_{index}"] = attempt + 1
    st.rerun()
