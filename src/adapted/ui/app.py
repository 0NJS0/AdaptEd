from __future__ import annotations

import os
from datetime import datetime

import streamlit as st

try:
    from adapted.ui.client import APIClient, APIError
except ImportError:
    from .client import APIClient, APIError

st.set_page_config(page_title="AdaptED", page_icon="🎓", layout="wide")

_BLOOM = {
    1: "Remembering",
    2: "Understanding",
    3: "Applying",
    4: "Analyzing",
    5: "Evaluating",
    6: "Creating",
}


def _bloom_label(level: int | None) -> str:
    if level is None:
        return "—"
    return f"{level} ({_BLOOM.get(level, '?')})"


def _client() -> APIClient:
    if "api_client" not in st.session_state:
        st.session_state.api_client = APIClient(
            os.getenv("ADAPTED_API_URL", "http://localhost:8001")
        )
    return st.session_state.api_client


def _user() -> dict:
    return st.session_state.get("user", {})


def _attempt(fn):
    try:
        return fn(), None
    except APIError as exc:
        return None, exc.detail
    except Exception as exc:  # noqa: BLE001
        return None, f"Connection error: {exc}"


def _show_error(res):
    _, err = res
    if err:
        st.error(err)
        return True
    return False


def _fmt(ts: str | None) -> str:
    if not ts:
        return "-"
    try:
        return datetime.fromisoformat(ts[:19]).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return str(ts)


# ====================================================================== AUTH


def auth_screen() -> None:
    st.title("🎓 AdaptED")
    tab_login, tab_register = st.tabs(["Login", "Register"])
    with tab_login:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Sign in", type="primary"):
            if not email or not password:
                st.error("Email and password are required")
            else:
                data, err = _attempt(lambda: _client().login(email, password))
                if err:
                    st.error(err)
                else:
                    _on_auth(data)
    with tab_register:
        name = st.text_input("Full name", key="reg_name")
        remail = st.text_input("Email", key="reg_email")
        rpass = st.text_input("Password (min 6 chars)", type="password", key="reg_pass")
        role = st.radio("I am a", ["student", "teacher"], horizontal=True)
        minutes = st.number_input(
            "Daily study minutes (students)",
            min_value=15,
            max_value=480,
            value=90,
            step=15,
            key="reg_minutes",
        )
        if st.button("Create account", type="primary"):
            if not name or not remail or len(rpass) < 6:
                st.error("Name, valid email and password (>=6 chars) are required")
            else:
                kwargs = {}
                if role == "student":
                    kwargs = {"daily_study_minutes": int(minutes)}
                data, err = _attempt(
                    lambda: _client().register(remail, rpass, name, role, **kwargs)
                )
                if err:
                    st.error(err)
                else:
                    _on_auth(data)


def _on_auth(data: dict) -> None:
    st.session_state.api_client.token = data["access_token"]
    st.session_state.user = data["user"]
    st.session_state.logged_in = True
    st.rerun()


def logout() -> None:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.api_client = APIClient()
    st.rerun()


def _ensure_client() -> bool:
    if not st.session_state.get("logged_in"):
        auth_screen()
        return False
    return True


# ==================================================================== SIDEBAR


_NAV_ICONS = {
    "Dashboard": "🏠",
    "Curriculum": "📋",
    "Class": "📊",
    "Review Queue": "🕵️",
    "OBE Mapping": "🧭",
    "Agent Console": "🛰️",
    "Operations": "🛠️",
    "Study Plan": "📅",
    "Learn": "📖",
    "Quizzes": "📝",
    "My Progress": "📈",
    "Recommendations": "💡",
}

# Light, version-safe polish only: gentle spacing + hover, no element hiding.
_SIDEBAR_CSS = """
<style>
section[data-testid="stSidebar"] div[role="radiogroup"] label {
    padding: 4px 8px; border-radius: 8px;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
    background: rgba(120,140,170,.12);
}
section[data-testid="stSidebar"] div[role="radiogroup"] label p { font-size: 15px; }
</style>
"""


def _clear_console_view() -> None:
    """Leaving the console when the user picks a sidebar page."""
    st.session_state.view = None


def sidebar() -> str | None:
    user = _user()
    role = user.get("role", "student")
    st.sidebar.markdown(_SIDEBAR_CSS, unsafe_allow_html=True)
    st.sidebar.markdown("## 🎓 AdaptED")
    st.sidebar.caption(f"**{user.get('full_name', '')}** · {role.title()}")
    st.sidebar.divider()

    nav = ["Dashboard"]
    if role == "teacher":
        nav += ["Curriculum", "Class", "Review Queue", "OBE Mapping", "Operations"]
    else:
        nav += ["Study Plan", "Learn", "Quizzes", "My Progress", "Recommendations"]

    # A button on the page can request a navigation by setting _pending_nav.
    # We must apply it BEFORE the radio widget is created on the next run
    # (a widget's key cannot be modified after it is instantiated).
    pending = st.session_state.pop("_pending_nav", None)
    if pending in nav:
        st.session_state["nav_radio"] = pending

    choice = st.sidebar.radio(
        "Menu",
        nav,
        key="nav_radio",
        label_visibility="collapsed",
        format_func=lambda x: f"{_NAV_ICONS.get(x, '•')}  {x}",
        on_change=_clear_console_view,
    )
    st.sidebar.divider()
    if st.sidebar.button("🚪 Sign out", use_container_width=True):
        logout()
    return choice


def top_nav() -> None:
    """A slim upper navigation bar with a separate entry to the Agent Console.

    Teacher-only. The console opens as its own view (independent of the sidebar
    menu) so it reads as a distinct tool; picking any sidebar page returns here.
    """
    user = _user()
    if user.get("role") != "teacher":
        return
    in_console = st.session_state.get("view") == "agent_console"
    left, right = st.columns([0.72, 0.28])
    with left:
        st.markdown("### 🛰️ Agent Console" if in_console else "🎓 **AdaptED**")
    with right:
        if in_console:
            if st.button("← Back to app", use_container_width=True):
                st.session_state.view = None
                st.rerun()
        elif st.button("🛰️ Open Agent Console", use_container_width=True):
            st.session_state.view = "agent_console"
            st.rerun()
    st.divider()


# ============================================================ COMMON WIDGETS


def _course_options(client: APIClient) -> dict[str, str]:
    courses, _ = _attempt(client.list_courses)
    return {c["title"]: c["id"] for c in courses or []}


def _course_selector(label: str = "Select course") -> str | None:
    options = _course_options(_client())
    if not options:
        st.info("No courses available. A teacher must create a course and enroll you first.")
        return None
    title = st.selectbox(label, list(options.keys()))
    return options[title]


def _render_curriculum(curriculum: dict) -> None:
    if _show_error((None, curriculum.get("error"))):
        return
    for ch in curriculum.get("chapters", []):
        with st.expander(f"📘 {ch['title']}"):
            for t in ch.get("topics", []):
                diff = t.get("difficulty", 0.0)
                st.markdown(
                    f"**{t['title']}** "
                    f"<span style='color:gray'>· difficulty {diff:.2f} · </span>"
                    f"<span style='color:#777'>{t['id'][:8]}…</span>",
                    unsafe_allow_html=True,
                )
                if t.get("description"):
                    st.caption(t["description"])
                if t.get("objectives"):
                    st.markdown("Objectives: " + "; ".join(t["objectives"]))
                if t.get("prerequisites"):
                    st.markdown("Prereqs: " + "; ".join(t["prerequisites"]))


def _topic_options(curriculum: dict) -> dict[str, str]:
    topics: dict[str, str] = {}
    for ch in curriculum.get("chapters", []):
        for t in ch.get("topics", []):
            topics[f"{ch['title']} › {t['title']}"] = t["id"]
    return topics


# ============================================================ TEACHER VIEWS


def teacher_dashboard() -> None:
    st.header("📚 My Courses")
    client = _client()
    courses, err = _attempt(client.list_courses)
    if err:
        st.error(err)
        return

    with st.expander("➕ Create a new course", expanded=not courses), st.form("create_course"):
        title = st.text_input("Course title")
        subject = st.text_input("Subject", placeholder="mathematics")
        description = st.text_area("Description")
        exam_date = st.date_input("Exam date (optional)", value=None)
        if st.form_submit_button("Create course", type="primary"):
            _, cerr = _attempt(
                lambda: client.create_course(
                    title,
                    subject or None,
                    description or None,
                    str(exam_date) if exam_date else None,
                )
            )
            if cerr:
                st.error(cerr)
            else:
                st.success(f"Course '{title}' created")
                st.rerun()

    for c in courses or []:
        with st.container(border=True):
            st.markdown(f"### {c['title']}")
            st.caption(
                f"{c.get('subject') or 'no subject'} · {c.get('student_count', 0)} students · "
                f"status `{c.get('status')}` · created {_fmt(c.get('created_at'))}"
            )
            if c.get("description"):
                st.write(c["description"])
            st.session_state.setdefault("selected_course_id", None)
            b_open, b_clear, b_del = st.columns([2, 1, 1])
            if b_open.button("Open course", key=f"open_{c['id']}", use_container_width=True):
                st.session_state.selected_course_id = c["id"]
                st.session_state["_pending_nav"] = "Curriculum"
                st.rerun()
            if b_clear.button(
                "🧹 Clear contents", key=f"clear_{c['id']}", use_container_width=True
            ):
                confirm_clear_course(client, c["id"], c["title"])
            if b_del.button("🗑 Delete", key=f"del_{c['id']}", use_container_width=True):
                confirm_delete_course(client, c["id"], c["title"])


@st.dialog("Delete document")
def confirm_delete_document(
    client: APIClient, course_id: str, document_id: str, filename: str
) -> None:
    st.warning(
        f"Delete **`{filename}`**? This permanently removes the file, its search "
        "index, and the curriculum generated from it. This cannot be undone."
    )
    c1, c2 = st.columns(2)
    if c1.button("Cancel", use_container_width=True):
        st.rerun()
    if c2.button("Delete", type="primary", use_container_width=True):
        _, err = _attempt(lambda: client.delete_document(course_id, document_id))
        if err:
            st.error(err)
        else:
            st.toast(f"Deleted `{filename}`.")
            st.rerun()


@st.dialog("Clear course contents")
def confirm_clear_course(client: APIClient, course_id: str, title: str) -> None:
    st.warning(
        f"Clear **all contents** of `{title}`? This deletes its documents, "
        "curriculum, lessons, quizzes, and student progress. The course itself "
        "stays. This cannot be undone."
    )
    c1, c2 = st.columns(2)
    if c1.button("Cancel", use_container_width=True):
        st.rerun()
    if c2.button("Clear contents", type="primary", use_container_width=True):
        _, err = _attempt(lambda: client.clear_course_contents(course_id))
        if err:
            st.error(err)
        else:
            st.toast(f"Cleared all contents of `{title}`.")
            st.rerun()


@st.dialog("Delete course")
def confirm_delete_course(client: APIClient, course_id: str, title: str) -> None:
    st.warning(
        f"Permanently delete **`{title}`** and everything in it? Its documents, "
        "curriculum, lessons, quizzes, enrollments, and student progress will all "
        "be removed. This cannot be undone."
    )
    c1, c2 = st.columns(2)
    if c1.button("Cancel", use_container_width=True):
        st.rerun()
    if c2.button("Delete course", type="primary", use_container_width=True):
        _, err = _attempt(lambda: client.delete_course(course_id))
        if err:
            st.error(err)
        else:
            if st.session_state.get("selected_course_id") == course_id:
                st.session_state.selected_course_id = None
            st.toast(f"Deleted `{title}`.")
            st.rerun()


def _selected_course() -> str | None:
    cid = st.session_state.get("selected_course_id")
    return cid


def teacher_curriculum() -> None:
    client = _client()
    cid = _selected_course()
    if not cid:
        cid = _course_selector("Select a course to manage")
        if not cid:
            return

    course, err = _attempt(lambda: client.get_course(cid))
    if err:
        st.error(err)
        return
    st.header(f"📋 Curriculum — {course['title']}")

    tab_docs, tab_cur, tab_enroll = st.tabs(["Documents", "Curriculum", "Enroll students"])

    with tab_docs:
        upload_col, list_col = st.columns(2)
        with upload_col:
            st.subheader("Upload a textbook / notes")
            f = st.file_uploader("Choose a file (.md, .txt, .pdf, .docx)", key=f"up_{cid}")
            if f is not None and st.button("Upload document", type="primary"):
                data, uerr = _attempt(
                    lambda: client.upload_document(
                        cid, f.name, f.getvalue(), f.type or "application/octet-stream"
                    )
                )
                if uerr:
                    st.error(uerr)
                else:
                    st.success(
                        f"Uploaded **{data['filename']}**. Click "
                        "**Analyze curriculum (agent run)** below to process it."
                    )
        with list_col:
            st.subheader("Uploaded documents")
            docs, derr = _attempt(lambda: client.list_documents(cid))
            if derr:
                st.error(derr)
            elif not docs:
                st.caption("No documents uploaded yet.")
            else:
                _status_dot = {"ready": "🟢", "processing": "🟡", "uploaded": "⚪", "error": "🔴"}
                for d in docs or []:
                    with st.container(border=True):
                        info, ddel = st.columns([0.85, 0.15])
                        with info:
                            st.markdown(f"📄 **{d['filename']}**")
                            st.caption(
                                f"{_status_dot.get(d.get('status'), '•')} {d.get('status', 'unknown')} "
                                f"· {(d.get('size_bytes', 0) or 0) / 1024:.1f} KB"
                            )
                        if ddel.button(
                            "🗑", key=f"del_doc_{d['id']}", help="Delete this document"
                        ):
                            confirm_delete_document(client, cid, d["id"], d["filename"])

        if st.button("⚙️ Analyze curriculum (agent run)", type="primary", key=f"analyze_{cid}"):
            doc_id = None
            docs, _ = _attempt(lambda: client.list_documents(cid))
            if docs:
                doc_id = docs[0]["id"]
            if not doc_id:
                st.error("Upload a document first")
            else:
                _run_analysis(cid, doc_id)

    with tab_cur:
        cur, cerr = _attempt(lambda: client.curriculum(cid))
        if cerr:
            st.error(cerr)
        else:
            _render_curriculum(cur)

    with tab_enroll:
        st.subheader("Enroll a student")
        students, serr = _attempt(lambda: client.class_students(cid))
        if serr and "404" in str(serr):
            students = []
        st.write("Students already in this course:")
        for s in students or []:
            grade = s.get("grade_level")
            st.markdown(
                f"- **{s['name']}** `{s['student_id']}`" + (f" — grade {grade}" if grade else "")
            )
        enrolled_ids = {s["student_id"] for s in students or []}

        st.markdown("**Find a student to enroll**")
        q = st.text_input(
            "Search by name or email", key=f"search_{cid}", placeholder="e.g. Rahim or rahim@…"
        )
        found = []
        if q.strip():
            found, ferr = _attempt(lambda: client.search_users(q, role="student", limit=20))
            if ferr:
                st.error(ferr)
        options = {f"{u['full_name']} ({u['email']})": u["id"] for u in found or []}
        if options:
            pick = st.selectbox("Select a student", list(options.keys()), key=f"pick_{cid}")
            if st.button("Enroll selected student", key=f"enrollsel_{cid}"):
                target = options[pick]
                if target in enrolled_ids:
                    st.warning("That student is already enrolled")
                else:
                    _, eerr = _attempt(lambda: client.enroll(cid, target))
                    if eerr:
                        st.error(eerr)
                    else:
                        st.success("Enrolled")
                        st.rerun()
        elif q.strip():
            st.caption("No matching students found.")

        with st.expander("Or paste a raw student ID"):
            sid = st.text_input(
                "Student ID to enroll (paste the student's user id)", key=f"enroll_{cid}"
            )
            if st.button("Enroll by ID", key=f"enrollbtn_{cid}"):
                if not sid:
                    st.error("Enter a student ID")
                else:
                    _, eerr = _attempt(lambda: client.enroll(cid, sid))
                    if eerr:
                        st.error(eerr)
                    else:
                        st.success("Enrolled")


def _run_analysis(course_id: str, document_id: str) -> None:
    client = _client()
    res, err = _attempt(
        lambda: client.run_agent(
            "analyze_curriculum", {"course_id": course_id, "document_id": document_id}
        )
    )
    if err:
        st.error(err)
        return
    st.session_state.pending_task = {
        "task_id": res["task_id"],
        "label": "Curriculum analysis",
        "on_success": "Analysis complete — chapters and topics are now in the Curriculum tab.",
    }
    st.rerun()


def _render_pending_task(client: APIClient) -> None:
    """Global notifier for background agent tasks.

    Wrapped in ``st.fragment(run_every=…)`` so the badge polls the task itself
    and updates in place while the user keeps using the rest of the page. On
    success the payload (lesson / quiz / submit result) is stored in
    ``session_state`` and a full rerun renders it on the relevant page.
    """

    @st.fragment(run_every=4.0)
    def _notifier() -> None:
        pending = st.session_state.get("pending_task")
        if not pending:
            return
        task_id = pending["task_id"]
        label = pending.get("label", "Agent task")
        task, err = _attempt(lambda: client.get_task(task_id))
        if err:
            st.error(err)
            return
        status = task.get("status", "started")

        if status == "started":
            st.info(f"⏳ {label} is being generated (task `{task_id}`)…")
            st.caption("It runs in the background — you can keep using the app meanwhile.")
            if st.button("🔄 Refresh task status", key=f"refresh_{task_id}"):
                st.rerun()
        elif status == "success":
            if not _store_task_result(client, pending, task):
                return
            st.success(pending.get("on_success") or f"{label} completed successfully.")
            st.session_state.pop("pending_task", None)
            st.rerun()
        elif status == "failed":
            st.error(f"{label} failed: {task.get('error') or 'unknown error'}")
            st.session_state.pop("pending_task", None)
            st.rerun()
        else:
            st.warning(f"{label} status: {status}")

    _notifier()


def _store_task_result(client: APIClient, pending: dict, task: dict) -> bool:
    """Move a finished task's payload into session_state so the page can render it."""
    ctx = task.get("result") or {}
    kind = pending.get("kind")

    if kind == "lesson":
        lesson_id = (ctx.get("lesson_agent") or {}).get("lesson_id")
        if not lesson_id:
            st.error("Lesson task finished but produced no lesson")
            return False
        lesson, err = _attempt(lambda lid=lesson_id: client.get_lesson(lid))
        if err:
            st.error(err)
            return False
        st.session_state[f"lesson_{pending.get('topic_id', '')}"] = lesson
    elif kind == "quiz":
        quiz_id = (ctx.get("quiz_agent") or {}).get("quiz_id")
        if not quiz_id:
            st.error("Quiz task finished but produced no quiz")
            return False
        quiz, err = _attempt(lambda qid=quiz_id: client.get_quiz(qid))
        if err:
            st.error(err)
            return False
        st.session_state.current_quiz = quiz
        st.session_state.quiz_answers = {}
    elif kind == "submit":
        st.session_state.last_result = {
            "grading": ctx.get("grading_agent") or {},
            "performance": ctx.get("performance_agent") or {},
            "recommendation": ctx.get("recommendation_agent") or {},
            "adapted_plan": ctx.get("planner_agent") or {},
            "targeted_lesson": ctx.get("lesson_agent") or {},
            "reassessment_quiz": ctx.get("quiz_agent") or {},
        }
    return True


def teacher_class() -> None:
    client = _client()
    cid = _selected_course()
    if not cid:
        cid = _course_selector("Select a course for analytics")
        if not cid:
            return
    st.header("📊 Class analytics")

    analytics, aerr = _attempt(lambda: client.class_analytics(cid))
    if aerr:
        st.error(aerr)
        return
    st.metric("Students", analytics.get("student_count", 0))
    st.metric("Curriculum progress", f"{analytics.get('curriculum_progress', 0):.0%}")

    st.subheader("Topic mastery across the class")
    for t in analytics.get("topic_mastery", []):
        pct = t.get("avg_mastery", 0)
        color = "🟢" if pct >= 60 else "🟠" if pct >= 40 else "🔴"
        st.progress(
            min(pct / 100, 1.0),
            text=f"{color} {t.get('topic_title', t.get('topic_id'))} — {pct:.0f}%",
        )

    if analytics.get("topics_needing_attention"):
        st.warning(
            "Needs attention: "
            + ", ".join(
                t.get("topic_title", t.get("topic_id"))
                for t in analytics["topics_needing_attention"]
            )
        )

    st.subheader("Student grades")
    students, _ = _attempt(lambda: client.class_students(cid))
    for s in students or []:
        grade = s.get("grade_level")
        with st.expander(s["name"] + (f" — grade {grade}" if grade else "")):
            sid = s["student_id"]
            grades, gerr = _attempt(lambda sid=sid: client.student_grades(cid, sid))
            if gerr:
                st.error(gerr)
            else:
                for g in grades or []:
                    st.markdown(
                        f"- `{g['quiz_title']}` — {g.get('percentage', 0):.0f}% "
                        f"({g.get('score')}/{g.get('max_score')}) · {_fmt(g.get('submitted_at'))}"
                    )


def teacher_review_queue() -> None:
    st.header("🕵️ Review queue (AI-graded answers)")
    client = _client()
    items, err = _attempt(client.pending_review)
    if err:
        st.error(err)
        return
    if not items:
        st.info("Nothing to review. All grades are settled.")
        return
    for a in items:
        with st.expander(f"Q: {a.get('prompt', '')[:120]}…"):
            st.markdown(f"**Student response:**\n```\n{a.get('response')}\n```")
            st.caption(
                f"AI score {a.get('ai_score')} · confidence {a.get('ai_confidence', 0):.2f} · "
                f"type {a.get('question_type')}"
            )
            if a.get("explanation"):
                st.caption(f"AI explanation: {a['explanation']}")
            new_score = st.number_input(
                "Override score (0-1)",
                min_value=0.0,
                max_value=1.0,
                value=float(a.get("ai_score") or 0.0),
                step=0.1,
                key=f"score_{a['answer_id']}",
            )
            is_correct = st.checkbox("Mark correct", value=False, key=f"correct_{a['answer_id']}")
            if st.button("Apply override", key=f"apply_{a['answer_id']}"):
                aid, sc, ck = a["answer_id"], new_score, is_correct
                _, oerr = _attempt(
                    lambda aid=aid, sc=sc, ck=ck: client.override_grade(
                        aid, score=sc, is_correct=ck
                    )
                )
                if oerr:
                    st.error(oerr)
                else:
                    st.success("Grade overridden")
                    st.rerun()


# ============================================================ STUDENT VIEWS


def student_dashboard() -> None:
    st.header("📚 My Courses")
    client = _client()
    courses, err = _attempt(client.list_courses)
    if err:
        st.error(err)
        return
    if not courses:
        st.info("You are not enrolled in any course yet.")
        return
    for c in courses or []:
        with st.container(border=True):
            st.markdown(f"### {c['title']}")
            st.caption(
                f"{c.get('subject') or 'no subject'} · {c.get('student_count', 0)} students · status `{c.get('status')}`"
            )
            if st.button("Use this course", key=f"sel_{c['id']}"):
                st.session_state.selected_course_id = c["id"]
                st.rerun()


def _student_id() -> str:
    return _user().get("id", "")


def _course_id() -> str:
    return st.session_state.get("selected_course_id") or ""


def student_study_plan() -> None:
    client = _client()
    sid = _student_id()
    cid = _course_id()
    if not cid:
        cid = _course_selector("Pick a course to see your study plan")
        if not cid:
            return
    plan, err = _attempt(lambda: client.study_plan(sid, cid))
    if err:
        if "No study plan" in err:
            st.warning("No study plan yet. Generate one below.")
            if st.button("✨ Create my study plan", type="primary"):
                res, gerr = _attempt(
                    lambda: client.run_agent(
                        "create_plan",
                        {
                            "student_id": sid,
                            "course_id": cid,
                            "daily_minutes": _user().get("daily_study_minutes") or 90,
                        },
                    )
                )
                if gerr:
                    st.error(gerr)
                else:
                    st.session_state.pending_task = {
                        "task_id": res["task_id"],
                        "label": "Study plan creation",
                        "on_success": "Study plan created — it is now listed above.",
                    }
                    st.rerun()
        else:
            st.error(err)
        return
    st.header(f"📅 Study Plan v{plan['version']} — {plan['daily_minutes']} min/day")
    st.caption(
        f"Exam date: {plan.get('exam_date') or 'not set'} · status `{plan.get('status')}` · created {_fmt(plan.get('created_at'))}"
    )
    by_day: dict[int, list] = {}
    for item in plan.get("items", []):
        by_day.setdefault(item["day_index"], []).append(item)
    for day in sorted(by_day):
        with st.expander(f"Day {day}"):
            for it in by_day[day]:
                state = "✅" if it.get("status") == "done" else "⬜"
                st.markdown(f"{state} **{it['title']}** (~{it['estimated_minutes']} min)")
                st.caption(f"Goal: {it.get('goal', '')}")
                if it.get("reason"):
                    st.caption(f"Why: {it.get('reason', '')}")


def student_learn() -> None:
    client = _client()
    sid = _student_id()
    cid = _course_id()
    if not cid:
        cid = _course_selector("Pick a course to learn from")
        if not cid:
            return
    cur, err = _attempt(lambda: client.curriculum(cid))
    if err:
        st.error(err)
        return
    st.header("📖 Learn — pick a topic")
    topics = _topic_options(cur)
    if not topics:
        st.info("This course has no topics yet.")
        return
    pick = st.selectbox("Topic", list(topics.keys()))
    topic_id = topics[pick]
    level = st.selectbox("Level", ["standard", "beginner", "advanced"])
    if st.button("📝 Generate lesson", type="primary"):
        res, lerr = _attempt(
            lambda: client.generate_lesson(cid, topic_id, student_id=sid, level=level)
        )
        if lerr:
            st.error(lerr)
        else:
            st.session_state.pending_task = {
                "task_id": res["task_id"],
                "kind": "lesson",
                "topic_id": topic_id,
                "label": "Lesson generation",
                "on_success": f"Lesson for '{pick}' is ready — scroll down to see it.",
            }
            st.rerun()
    lesson = st.session_state.get(f"lesson_{topic_id}")
    if lesson:
        _render_lesson(lesson)


def _render_lesson(lesson: dict) -> None:
    st.subheader(lesson.get("title", "Lesson"))
    content = lesson.get("content") or {}
    for section in content.get("sections", []):
        st.markdown(f"### {section.get('name', '')}")
        st.markdown(section.get("content", ""))
    if content.get("summary"):
        st.info(content["summary"])


def student_quizzes() -> None:
    client = _client()
    sid = _student_id()
    cid = _course_id()
    if not cid:
        cid = _course_selector("Pick a course to be quizzed on")
        if not cid:
            return
    cur, _ = _attempt(lambda: client.curriculum(cid))
    topics = _topic_options(cur or {})
    st.header("📝 Quizzes")

    with st.expander("➕ Generate a quiz"):
        topic_pick = st.selectbox(
            "Topic (or whole course)", ["Whole course", *list(topics.keys())], key="quiz_topic"
        )
        count = st.slider("Number of questions", 3, 20, 5)
        difficulty = st.slider("Difficulty", 0.0, 1.0, 0.5, 0.1)
        quiz_type = st.selectbox("Quiz type", ["assessment", "reassessment", "exit_ticket"])
        if st.button("Generate quiz", type="primary"):
            topic_id = topics.get(topic_pick) if topic_pick != "Whole course" else None
            res, qerr = _attempt(
                lambda: client.generate_quiz(
                    cid,
                    topic_id=topic_id,
                    student_id=sid,
                    count=int(count),
                    difficulty=float(difficulty),
                    quiz_type=quiz_type,
                )
            )
            if qerr:
                st.error(qerr)
            else:
                st.session_state.pending_task = {
                    "task_id": res["task_id"],
                    "kind": "quiz",
                    "label": "Quiz generation",
                    "on_success": "Quiz is ready — it is loaded below.",
                }
                st.rerun()

    quiz = st.session_state.get("current_quiz")
    if not quiz:
        st.info("No quiz loaded. Generate one above.")
        return
    st.subheader(quiz.get("title", "Quiz"))
    st.caption(
        f"type `{quiz.get('quiz_type')}` · status `{quiz.get('status')}` · {len(quiz.get('questions', []))} questions"
    )
    answers = st.session_state.setdefault("quiz_answers", {})
    for q in quiz.get("questions", []):
        st.markdown(f"**Q:** {q['prompt']}")
        qtype = q.get("question_type")
        if qtype == "true_false":
            val = st.radio("Answer", ["True", "False"], key=f"q_{q['id']}", horizontal=True)
        elif q.get("choices"):
            val = st.radio("Answer", q["choices"], key=f"q_{q['id']}")
        else:
            val = st.text_input("Your answer", key=f"q_{q['id']}")
        answers[q["id"]] = {"value": val}

    if st.button("Submit quiz", type="primary"):
        res, serr = _attempt(lambda: client.submit_quiz(quiz["id"], answers))
        if serr:
            st.error(serr)
        else:
            st.session_state.pending_task = {
                "task_id": res["task_id"],
                "kind": "submit",
                "quiz_id": quiz["id"],
                "label": "Quiz grading & adaptive review",
                "on_success": "Quiz graded — results are shown below.",
            }
            st.rerun()

    result = st.session_state.get("last_result")
    if result and result.get("grading"):
        _render_quiz_result(result)


def _render_quiz_result(result: dict) -> None:
    grading = result.get("grading") or {}
    st.subheader("✅ Results")
    st.metric("Score", f"{grading.get('percentage', 0):.0f}%")
    st.progress(min(grading.get("percentage", 0) / 100, 1.0))
    perf = result.get("performance") or {}
    weak = perf.get("weak_topics", [])
    if weak:
        st.warning(
            "Weak topics: " + ", ".join(w.get("topic_title", w.get("topic_id", "")) for w in weak)
        )
    strong = perf.get("strong_topics", [])
    if strong:
        st.success(
            "Strong topics: "
            + ", ".join(s.get("topic_title", s.get("topic_id", "")) for s in strong)
        )
    rec = (result.get("recommendation") or {}).get("recommendation") or {}
    if rec:
        st.info(f"**Recommendation:** {rec.get('title', '')}")
        for r in rec.get("reasons", []):
            st.caption(f"- {r}")
    plan = result.get("adapted_plan") or {}
    if plan.get("valid"):
        st.success(
            f"Study plan updated to v{plan.get('version')} ({len(plan.get('items', []))} items)"
        )
    lesson = result.get("targeted_lesson") or {}
    if lesson.get("lesson_id"):
        st.info("A targeted lesson was generated for you. Check the Learn page.")
    reassess = result.get("reassessment_quiz")
    if reassess and reassess.get("quiz_id"):
        st.info(f"Reassessment quiz generated: `{reassess.get('quiz_id')}`")


def student_progress() -> None:
    client = _client()
    sid = _student_id()
    profile, err = _attempt(lambda: client.student_profile(sid))
    if err:
        st.error(err)
        return
    st.header("📈 My Progress")
    st.metric("Overall mastery", f"{profile.get('overall_mastery', 0):.0f}%")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Mastery by topic")
        for m in profile.get("mastery", []):
            st.progress(
                min(m["mastery"] / 100, 1.0), text=f"{m['topic_title']} — {m['mastery']:.0f}%"
            )
    with col2:
        st.subheader("Preferences")
        prefs = profile.get("preferences") or {}
        for k, v in prefs.items():
            st.markdown(f"- `{k}`: {v}")
        st.caption(f"Recent quiz: {_fmt((profile.get('recent_quiz') or {}).get('submitted_at'))}")


def student_recommendations() -> None:
    client = _client()
    sid = _student_id()
    recs, err = _attempt(lambda: client.recommendations(sid))
    if err:
        st.error(err)
        return
    st.header("💡 Recommendations")
    if not recs:
        st.info("No recommendations yet. Take a quiz to generate some.")
    for r in recs or []:
        with st.expander(f"{r.get('title')} — status `{r.get('status')}`"):
            st.caption(f"Action: {r.get('action')} · confidence {r.get('confidence', 0):.2f}")
            for reason in r.get("reasons", []):
                st.markdown(f"- {reason}")
            if st.button("Mark applied", key=f"app_{r['id']}"):
                rid = r["id"]
                _, aerr = _attempt(
                    lambda sid=sid, rid=rid: client.update_recommendation(sid, rid, "applied")
                )
                if aerr:
                    st.error(aerr)
                else:
                    st.success("Marked as applied")
                    st.rerun()


# ======================================================= OBE MAPPING (teacher)


def teacher_obe() -> None:
    client = _client()
    st.header("🧭 OBE Mapping Assistant")
    st.caption(
        "Upload an AIUB CS course outline (.pdf, .docx, .txt, .md). The OBE agent "
        "extracts the CO ↔ PO structure, validates it against the AIUB CS OBE Manual, "
        "suggests corrected mappings, and drafts the mapping summary. **Your file is "
        "never stored or modified.**"
    )

    up_col, opt_col = st.columns([3, 2])
    with up_col:
        f = st.file_uploader(
            "Course outline", type=["pdf", "docx", "txt", "md"], key="obe_file"
        )
    with opt_col:
        polish = st.checkbox(
            "Polish summary with LLM",
            value=False,
            help="Optional. Uses the configured LLM provider (needs an API key). "
            "Leave off for the deterministic, offline summary.",
        )

    if f is not None and st.button("🔍 Analyze outline", type="primary"):
        res, err = _attempt(
            lambda: client.analyze_obe(
                f.name, f.getvalue(), f.type or "application/octet-stream", polish
            )
        )
        if err:
            st.error(err)
        else:
            st.session_state.obe_result = res
            st.session_state.obe_filename = f.name

    result = st.session_state.get("obe_result")
    if result:
        _render_obe_result(result, st.session_state.get("obe_filename", "outline"))

    with st.expander("⚡ Quick check — map a single Course Outcome"):
        desc = st.text_area(
            "CO description",
            placeholder="e.g. Design a solution for a complex engineering problem using UML.",
            key="obe_quick_desc",
        )
        if st.button("Suggest mapping", key="obe_quick_btn"):
            if not desc.strip():
                st.warning("Enter a CO description first.")
            else:
                res, err = _attempt(lambda: client.suggest_obe(desc))
                if err:
                    st.error(err)
                else:
                    for s in res.get("suggestions", []):
                        st.markdown(
                            f"**Bloom:** {_bloom_label(s.get('suggested_bloom_level'))} · "
                            f"**PO:** {', '.join(s.get('suggested_pos') or []) or '—'}"
                        )
                        kpa = s.get("suggested_kpa", {})
                        st.caption(
                            f"K: {', '.join(kpa.get('k', [])) or '—'} · "
                            f"P: {', '.join(kpa.get('p', [])) or '—'} · "
                            f"A: {', '.join(kpa.get('a', [])) or '—'}"
                        )
                        for r in s.get("rationale", []):
                            st.caption(f"• {r}")

    _obe_authoring_tools(client)


def _obe_authoring_tools(client: APIClient) -> None:
    """The OBE Authoring agent: generate compliant COs, and rewrite a flagged one."""
    with st.expander("✍️ Author new Course Outcomes (OBE Authoring agent)"):
        st.caption(
            "Generate OBE-compliant Course Outcomes with a proper Bloom spread, "
            "suggested PO and K-P-A — ready to drop into a new outline."
        )
        a1, a2 = st.columns(2)
        title = a1.text_input("Course title", key="author_title", placeholder="e.g. Data Structures")
        subject = a2.text_input("Subject", key="author_subject", placeholder="e.g. computer science")
        topics_raw = st.text_input(
            "Key topics (comma-separated, optional)",
            key="author_topics",
            placeholder="e.g. sorting, trees, graphs, complexity",
        )
        n = st.slider("How many COs", 2, 8, 4, key="author_count")
        if st.button("Generate Course Outcomes", key="author_btn"):
            topics = [t.strip() for t in topics_raw.split(",") if t.strip()]
            res, err = _attempt(
                lambda: client.author_obe(
                    course_title=title, subject=subject, topics=topics, count=int(n)
                )
            )
            if err:
                st.error(err)
            else:
                for c in res.get("cos", []):
                    with st.container(border=True):
                        st.markdown(
                            f"**{c['id']}** — {c['description']}"
                        )
                        kpa = c.get("suggested_kpa", {})
                        st.caption(
                            f"Bloom {_bloom_label(c.get('bloom_level'))} · "
                            f"PO {', '.join(c.get('suggested_pos') or []) or '—'} · "
                            f"K {', '.join(kpa.get('k', [])) or '—'} / "
                            f"P {', '.join(kpa.get('p', [])) or '—'} / "
                            f"A {', '.join(kpa.get('a', [])) or '—'}"
                        )

    with st.expander("🔧 Improve a Course Outcome"):
        st.caption(
            "Rewrite a CO the validator flagged so its verb, Bloom level and PO/K-P-A line up."
        )
        desc = st.text_area(
            "Course Outcome to fix",
            key="improve_desc",
            placeholder="e.g. Explain the design of a complex system using UML. (tagged Bloom L5)",
        )
        lvl = st.selectbox(
            "Target Bloom level (optional)",
            ["auto", 1, 2, 3, 4, 5, 6],
            key="improve_level",
            help="1 Remember · 2 Understand · 3 Apply · 4 Analyze · 5 Evaluate · 6 Create",
        )
        if st.button("Improve outcome", key="improve_btn"):
            if not desc.strip():
                st.warning("Enter a Course Outcome first.")
            else:
                target = None if lvl == "auto" else int(lvl)
                res, err = _attempt(lambda: client.improve_obe(desc, target_level=target))
                if err:
                    st.error(err)
                else:
                    imp = res.get("improved", {})
                    st.markdown(f"**Original:** {imp.get('original_description')}")
                    st.success(f"**Improved:** {imp.get('improved_description')}")
                    kpa = imp.get("suggested_kpa", {})
                    st.caption(
                        f"Bloom {_bloom_label(imp.get('bloom_level'))} · "
                        f"PO {', '.join(imp.get('suggested_pos') or []) or '—'} · "
                        f"K {', '.join(kpa.get('k', [])) or '—'} / "
                        f"P {', '.join(kpa.get('p', [])) or '—'} / "
                        f"A {', '.join(kpa.get('a', [])) or '—'}"
                    )
                    for ch in imp.get("changes", []):
                        st.markdown(f"- 🔧 {ch}")


def _render_obe_result(result: dict, filename: str) -> None:
    ext = result.get("extraction", {})
    report = result.get("report", {})
    course = ext.get("course", {})
    errors = report.get("error_count", 0)
    warnings = report.get("warning_count", 0)

    st.markdown(f"### {course.get('code', '')} — {course.get('title', filename)}")
    if course.get("semester"):
        st.caption(f"{course.get('semester')} · {course.get('credit') or '?'} credit")

    if errors == 0:
        st.success(
            f"✅ Mapping consistent — no blocking errors. "
            f"{warnings} advisory warning(s) to review."
        )
    else:
        st.error(
            f"❌ {errors} blocking error(s) and {warnings} warning(s). "
            "Correct before sign-off."
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Course Outcomes", len(ext.get("cos", [])))
    m2.metric("PO indicators", len(ext.get("po_indicators", [])))
    m3.metric("Errors", errors)
    m4.metric("Warnings", warnings)

    tab_m, tab_f, tab_s, tab_sum = st.tabs(
        ["CO ↔ PO Matrix", f"Findings ({len(report.get('findings', []))})",
         "Suggested fixes", "Summary"]
    )

    with tab_m:
        co_rows = [
            {
                "CO": co.get("id"),
                "Description": co.get("description"),
                "Verb": co.get("verb"),
                "Bloom": _bloom_label(co.get("bloom_level")),
                "Mapped PO": ", ".join(co.get("mapped_pos", [])),
            }
            for co in ext.get("cos", [])
        ]
        if co_rows:
            st.dataframe(co_rows, use_container_width=True, hide_index=True)
        st.markdown("**PO indicators & K–P–A**")
        po_rows = [
            {
                "Indicator": p.get("id"),
                "Domain / Bloom": f"{p.get('bloom_domain', '').title()} L{p.get('bloom_level')}",
                "K": ", ".join(dict.fromkeys(p.get("kpa", {}).get("k", []))),
                "P": ", ".join(dict.fromkeys(p.get("kpa", {}).get("p", []))),
                "A": ", ".join(dict.fromkeys(p.get("kpa", {}).get("a", []))),
            }
            for p in ext.get("po_indicators", [])
        ]
        if po_rows:
            st.dataframe(po_rows, use_container_width=True, hide_index=True)

    with tab_f:
        findings = report.get("findings", [])
        if not findings:
            st.success("No issues detected — the mapping is internally consistent.")
        for fd in findings:
            sev = fd.get("severity")
            msg = f"**{fd.get('location')}** · `{fd.get('code')}` — {fd.get('message')}"
            if sev == "error":
                st.error(msg)
            elif sev == "warning":
                st.warning(msg)
            else:
                st.info(msg)
            if fd.get("suggestion"):
                st.caption(f"💡 Suggested fix: {fd['suggestion']}")

    with tab_s:
        for s in result.get("suggestions", []):
            with st.container(border=True):
                st.markdown(
                    f"**{s.get('co_id')}** · verb “{s.get('verb')}” → "
                    f"Bloom **{_bloom_label(s.get('suggested_bloom_level'))}** · "
                    f"PO **{', '.join(s.get('suggested_pos') or []) or '—'}**"
                )
                kpa = s.get("suggested_kpa", {})
                st.caption(
                    f"Suggested K–P–A · K: {', '.join(kpa.get('k', [])) or '—'} · "
                    f"P: {', '.join(kpa.get('p', [])) or '—'} · "
                    f"A: {', '.join(kpa.get('a', [])) or '—'}"
                )
                for r in s.get("rationale", []):
                    st.caption(f"• {r}")

    with tab_sum:
        md = result.get("summary_markdown", "")
        st.download_button(
            "⬇ Download summary (.md)",
            data=md,
            file_name=f"OBE_Summary_{course.get('code', 'course').replace(' ', '_')}.md",
            mime="text/markdown",
        )
        st.markdown(md)


# ======================================================= AGENT CONSOLE (teacher)

_AGENT_ROSTER = [
    ("supervisor", "🧭 Supervisor"),
    ("curriculum_agent", "📖 Curriculum"),
    ("planner_agent", "📅 Planner"),
    ("lesson_agent", "📝 Lesson"),
    ("quiz_agent", "❓ Quiz"),
    ("grading_agent", "✅ Grading"),
    ("performance_agent", "📊 Performance"),
    ("recommendation_agent", "💡 Recommendation"),
    ("obe_agent", "🧭 OBE Mapping"),
]

_STATUS_ICON = {
    "started": "⏳",
    "running": "⏳",
    "success": "✅",
    "failed": "❌",
    "cancelled": "🚫",
    "paused": "⏸️",
    "awaiting_approval": "🕓",
    "retrying": "🔁",
}


def _sicon(status: str | None) -> str:
    return _STATUS_ICON.get(status or "", "•")


def agent_console() -> None:
    client = _client()
    st.header("🛰️ Agent Console")
    st.caption(
        "Live observability and control for the multi-agent pipeline — dashboard, execution trace, "
        "graph, token/cost, logs, memory, human-in-the-loop controls and the final report."
    )

    tabs = st.tabs(
        [
            "📊 Dashboard",
            "🕸️ Execution graph",
            "📡 Live trace",
            "✉️ Messages",
            "🪙 Tokens & cost",
            "🪵 Logs & errors",
            "🧠 Memory",
            "🎛️ Controls",
            "📄 Report",
        ]
    )

    with tabs[0]:
        _console_dashboard(client)
    with tabs[1]:
        _console_graph(client)
    with tabs[2]:
        _console_trace(client)
    with tabs[3]:
        _console_messages(client)
    with tabs[4]:
        _console_usage(client)
    with tabs[5]:
        _console_logs(client)
    with tabs[6]:
        _console_memory(client)
    with tabs[7]:
        _console_controls(client)
    with tabs[8]:
        _console_report(client)


def _console_dashboard(client: APIClient) -> None:
    tasks, err = _attempt(lambda: client.agent_tasks(limit=100))
    if err:
        st.error(err)
        return
    tasks = tasks or []
    msgs, _ = _attempt(lambda: client.agent_messages(limit=200))
    msgs = msgs or []

    running = [t for t in tasks if t["status"] in ("started", "running", "retrying")]
    done = [t for t in tasks if t["status"] in ("success", "failed", "cancelled")]
    ok = [t for t in done if t["status"] == "success"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total runs", len(tasks))
    c2.metric("Running now", len(running))
    c3.metric("Success rate", f"{(len(ok) / len(done) * 100) if done else 0:.0f}%")
    c4.metric("Total cost (est.)", f"${sum(t.get('cost_usd', 0) or 0 for t in tasks):.4f}")

    st.subheader("Active agents")
    counts: dict[str, int] = {}
    for m in msgs:
        counts[m["receiver"]] = counts.get(m["receiver"], 0) + 1
    active_receivers = {m["receiver"] for t in running for m in msgs if m["task_id"] == t["task_id"]}
    cols = st.columns(3)
    for i, (name, label) in enumerate(_AGENT_ROSTER):
        with cols[i % 3].container(border=True):
            dot = "🟢" if name in active_receivers else "⚪"
            st.markdown(f"{dot} **{label}**")
            st.caption(f"`{name}` · {counts.get(name, 0)} recent messages")

    st.subheader("Recent workflow runs")
    if not tasks:
        st.info("No agent runs yet. Trigger a workflow (e.g. analyze curriculum, submit a quiz, or analyze an outline).")
        return
    rows = [
        {
            "": _sicon(t["status"]),
            "Intent": t["intent"],
            "Status": t["status"],
            "Duration": f"{t.get('duration_ms', 0)} ms",
            "Tokens": (t.get("prompt_tokens", 0) or 0) + (t.get("completion_tokens", 0) or 0),
            "Cost": f"${t.get('cost_usd', 0) or 0:.4f}",
            "Task": t["task_id"],
            "Started": _fmt(t.get("started_at")),
        }
        for t in tasks[:25]
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _console_graph(client: APIClient) -> None:
    st.caption("The LangGraph pipeline. Pick a run to highlight the path it actually took.")
    tasks, _ = _attempt(lambda: client.agent_tasks(limit=50))
    tasks = tasks or []
    opts = {"— whole pipeline —": None}
    for t in tasks:
        opts[f"{_sicon(t['status'])} {t['intent']} · {t['task_id']}"] = t["task_id"]
    pick = st.selectbox("Highlight run", list(opts.keys()), key="graph_pick")
    graph, err = _attempt(lambda: client.agent_graph(opts[pick]))
    if err:
        st.error(err)
        return
    st.graphviz_chart(graph.get("dot", ""), use_container_width=True)
    if graph.get("visited"):
        st.caption("Path: " + " → ".join(graph["visited"]))


def _console_trace(client: APIClient) -> None:
    st.caption("Live, auto-refreshing trace of a single run's agent hops.")
    tasks, _ = _attempt(lambda: client.agent_tasks(limit=50))
    tasks = tasks or []
    if not tasks:
        st.info("No runs to trace yet.")
        return
    opts = {f"{_sicon(t['status'])} {t['intent']} · {t['task_id']}": t["task_id"] for t in tasks}
    pick = st.selectbox("Run to trace", list(opts.keys()), key="trace_pick")
    task_id = opts[pick]

    @st.fragment(run_every=3.0)
    def _trace() -> None:
        task, terr = _attempt(lambda: client.get_task(task_id))
        if terr:
            st.error(terr)
            return
        st.markdown(
            f"**{_sicon(task['status'])} {task['intent']}** — status `{task['status']}` · "
            f"{task.get('duration_ms', 0)} ms · {task.get('llm_calls', 0)} LLM calls"
        )
        if task.get("status") in ("started", "running", "retrying"):
            st.caption("🔴 live — refreshing every 3s")
        mm, _e = _attempt(lambda: client.agent_messages(task_id=task_id, limit=100))
        mm = list(reversed(mm or []))  # oldest first
        if not mm:
            st.caption("Waiting for the first agent hop…")
        for m in mm:
            st.markdown(
                f"{_sicon(m['status'])} `{m['sender']} → {m['receiver']}` "
                f"**{m['action']}** · {m['status']} · {m.get('duration_ms', 0)} ms"
            )
            if m.get("error"):
                st.caption(f"⚠️ {m['error']}")
        if task.get("error"):
            st.error(task["error"])

    _trace()


def _console_messages(client: APIClient) -> None:
    st.caption("Full agent-to-agent communication history (the message bus).")
    task_filter = st.text_input("Filter by task id (optional)", key="msg_filter")
    msgs, err = _attempt(
        lambda: client.agent_messages(task_id=task_filter or None, limit=300)
    )
    if err:
        st.error(err)
        return
    rows = [
        {
            "": _sicon(m["status"]),
            "From": m["sender"],
            "To": m["receiver"],
            "Action": m["action"],
            "Status": m["status"],
            "ms": m.get("duration_ms", 0),
            "Task": m["task_id"],
        }
        for m in (msgs or [])
    ]
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No messages yet.")


def _console_usage(client: APIClient) -> None:
    usage, err = _attempt(lambda: client.agent_usage(limit=300))
    if err:
        st.error(err)
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prompt tokens", f"{usage.get('prompt_tokens', 0):,}")
    c2.metric("Completion tokens", f"{usage.get('completion_tokens', 0):,}")
    c3.metric("LLM calls", usage.get("llm_calls", 0))
    c4.metric("Est. cost", f"${usage.get('cost_usd', 0):.4f}")
    st.caption(
        "Costs are estimates from configured per-1K-token prices (0 for free models; "
        "in mock mode tokens are approximated from text length). Set `LLM_PRICE_INPUT_PER_1K` / "
        "`LLM_PRICE_OUTPUT_PER_1K` in `.env` for real rates."
    )
    by_intent = usage.get("by_intent", [])
    if by_intent:
        st.subheader("By workflow")
        st.dataframe(
            [
                {
                    "Intent": r["intent"],
                    "Runs": r["tasks"],
                    "Total tokens": r["total_tokens"],
                    "Cost": f"${r['cost_usd']:.4f}",
                }
                for r in by_intent
            ],
            use_container_width=True,
            hide_index=True,
        )


def _console_logs(client: APIClient) -> None:
    st.subheader("Failed runs")
    tasks, _ = _attempt(lambda: client.agent_tasks(limit=100))
    failed = [t for t in (tasks or []) if t["status"] == "failed"]
    if not failed:
        st.success("No failed runs.")
    for t in failed:
        with st.expander(f"❌ {t['intent']} · {t['task_id']} · {_fmt(t.get('started_at'))}"):
            st.error(t.get("error") or "unknown error")
            st.json(t.get("result") or {})

    st.subheader("Failed messages")
    msgs, _ = _attempt(lambda: client.agent_messages(limit=300))
    failed_msgs = [m for m in (msgs or []) if m["status"] == "failed"]
    for m in failed_msgs:
        st.markdown(f"❌ `{m['sender']}→{m['receiver']}` **{m['action']}** — {m.get('error')}")
    if not failed_msgs:
        st.caption("No failed messages.")

    st.subheader("Audit log")
    logs, _ = _attempt(lambda: client.audit_logs(limit=50))
    for l in logs or []:
        st.markdown(
            f"- `{l['action']}` on `{l.get('resource_type')}/{l.get('resource_id')}` "
            f"by {l.get('role')} — {_fmt(l.get('timestamp'))}"
        )


def _console_memory(client: APIClient) -> None:
    st.caption("Inspect the persistent student memory and the curriculum (RAG) memory.")
    cid = _course_selector("Course")
    if not cid:
        return
    students, serr = _attempt(lambda: client.class_students(cid))
    if serr:
        st.error(serr)
        return
    if not students:
        st.info("No students enrolled in this course.")
        return
    opts = {f"{s['name']} ({s['student_id'][:8]}…)": s["student_id"] for s in students}
    pick = st.selectbox("Student", list(opts.keys()), key="mem_student")
    sid = opts[pick]

    profile, perr = _attempt(lambda: client.student_profile(sid))
    if perr:
        st.error(perr)
        return
    st.metric("Overall mastery", f"{profile.get('overall_mastery', 0):.0f}%")
    mc1, mc2 = st.columns(2)
    with mc1:
        st.subheader("Topic mastery")
        for m in profile.get("mastery", []):
            st.progress(
                min(m["mastery"] / 100, 1.0), text=f"{m['topic_title']} — {m['mastery']:.0f}%"
            )
        if not profile.get("mastery"):
            st.caption("No mastery recorded yet.")
    with mc2:
        st.subheader("Preferences")
        for k, v in (profile.get("preferences") or {}).items():
            st.markdown(f"- `{k}`: {v}")
        st.subheader("Recommendations")
        recs, _ = _attempt(lambda: client.recommendations(sid))
        for r in (recs or [])[:5]:
            st.markdown(f"- {r.get('title')} · `{r.get('status')}`")
        if not recs:
            st.caption("No recommendations yet.")

    with st.expander("🔎 Raw profile JSON"):
        st.json(profile)


def _console_controls(client: APIClient) -> None:
    st.caption("Human-in-the-loop: approve gated runs, and pause / cancel / retry / resume.")
    tasks, err = _attempt(lambda: client.agent_tasks(limit=60))
    if err:
        st.error(err)
        return
    tasks = tasks or []

    def _do(task_id: str, action: str) -> None:
        res, aerr = _attempt(lambda: client.task_action(task_id, action))
        if aerr:
            st.error(aerr)
        else:
            st.toast(res.get("message", action))
            st.rerun()

    awaiting = [t for t in tasks if t["status"] == "awaiting_approval"]
    st.subheader(f"🕓 Awaiting approval ({len(awaiting)})")
    for t in awaiting:
        with st.container(border=True):
            st.markdown(f"**{t['intent']}** · `{t['task_id']}`")
            st.caption(f"workflow `{t.get('workflow')}` · submitted {_fmt(t.get('started_at'))}")
            a, b = st.columns(2)
            if a.button("✅ Approve", key=f"appr_{t['task_id']}", use_container_width=True):
                _do(t["task_id"], "approve")
            if b.button("🚫 Reject", key=f"rej_{t['task_id']}", use_container_width=True):
                _do(t["task_id"], "reject")
    if not awaiting:
        st.caption("Nothing awaiting approval.")

    running = [t for t in tasks if t["status"] in ("started", "running", "retrying")]
    st.subheader(f"⏳ Running ({len(running)})")
    for t in running:
        with st.container(border=True):
            st.markdown(f"**{t['intent']}** · `{t['task_id']}`")
            a, b = st.columns(2)
            if a.button("⏸️ Pause", key=f"pause_{t['task_id']}", use_container_width=True):
                _do(t["task_id"], "pause")
            if b.button("🛑 Cancel", key=f"cancel_{t['task_id']}", use_container_width=True):
                _do(t["task_id"], "cancel")
    if not running:
        st.caption("No runs in progress.")

    stopped = [t for t in tasks if t["status"] in ("failed", "cancelled", "paused")]
    st.subheader(f"🔁 Failed / paused / cancelled ({len(stopped)})")
    for t in stopped[:15]:
        with st.container(border=True):
            st.markdown(f"{_sicon(t['status'])} **{t['intent']}** · `{t['task_id']}` — {t['status']}")
            if t.get("error"):
                st.caption(f"⚠️ {t['error']}")
            a, b = st.columns(2)
            if a.button("🔁 Retry", key=f"retry_{t['task_id']}", use_container_width=True):
                _do(t["task_id"], "retry")
            if b.button("▶️ Resume", key=f"resume_{t['task_id']}", use_container_width=True):
                _do(t["task_id"], "resume")

    with st.expander("🚀 Launch a workflow with an approval gate (advanced)"):
        st.caption(
            "Submits a workflow that will not run until you approve it above. "
            "Payload is JSON, e.g. `{\"course_id\": \"…\", \"document_id\": \"…\"}`."
        )
        intent = st.selectbox(
            "Intent",
            [
                "analyze_curriculum",
                "create_plan",
                "generate_lesson",
                "generate_quiz",
                "quiz_submit",
                "generate_recommendation",
                "analyze_outline",
            ],
            key="launch_intent",
        )
        payload_txt = st.text_area("Payload (JSON)", value="{}", key="launch_payload")
        if st.button("Submit for approval", key="launch_btn"):
            import json as _json

            try:
                payload = _json.loads(payload_txt or "{}")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Invalid JSON: {exc}")
            else:
                res, lerr = _attempt(
                    lambda: client.run_agent(intent, payload, require_approval=True)
                )
                if lerr:
                    st.error(lerr)
                else:
                    st.success(
                        f"Submitted `{res['task_id']}` (status: {res['status']}). "
                        "Approve it above to run."
                    )
                    st.rerun()


def _console_report(client: APIClient) -> None:
    st.caption("The final output of a completed run.")
    tasks, _ = _attempt(lambda: client.agent_tasks(limit=60))
    finished = [t for t in (tasks or []) if t["status"] in ("success", "failed", "cancelled")]
    if not finished:
        st.info("No completed runs yet.")
        return
    opts = {f"{_sicon(t['status'])} {t['intent']} · {t['task_id']}": t["task_id"] for t in finished}
    pick = st.selectbox("Completed run", list(opts.keys()), key="report_pick")
    task, err = _attempt(lambda: client.get_task(opts[pick]))
    if err:
        st.error(err)
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", task["status"])
    c2.metric("Duration", f"{task.get('duration_ms', 0)} ms")
    c3.metric("Tokens", (task.get("prompt_tokens", 0) or 0) + (task.get("completion_tokens", 0) or 0))
    c4.metric("Cost", f"${task.get('cost_usd', 0) or 0:.4f}")
    if task.get("error"):
        st.error(task["error"])

    result = task.get("result") or {}
    # OBE runs carry a ready-made markdown summary
    obe = result.get("obe_agent") or {}
    if obe.get("summary_markdown"):
        st.subheader("OBE mapping summary")
        st.markdown(obe["summary_markdown"])

    st.subheader("Per-agent output")
    if not result:
        st.caption("No structured result recorded.")
    for agent_name, output in result.items():
        with st.expander(f"🔹 {agent_name}"):
            st.json(output)


# ============================================================ OPS (teacher)


def operations_view() -> None:
    client = _client()
    st.header("🛠 Operations")
    tab_tasks, tab_msgs, tab_logs, tab_health = st.tabs(
        ["Agent tasks", "Agent messages", "Audit logs", "Health"]
    )
    with tab_tasks:
        if st.button("🔄 Refresh tasks", key="refresh_tasks"):
            st.rerun()
        tasks, err = _attempt(lambda: client.agent_tasks(limit=30))
        if err:
            st.error(err)
        else:
            for t in tasks or []:
                st.markdown(
                    f"- `{t['intent']}` — {t['status']} · {t.get('duration_ms', 0)}ms · {_fmt(t.get('started_at'))}"
                    + (f" ⚠️ {t.get('error')}" if t.get("error") else "")
                )
    with tab_msgs:
        msgs, err = _attempt(lambda: client.agent_messages(limit=50))
        if err:
            st.error(err)
        else:
            for m in msgs or []:
                st.markdown(
                    f"- `{m['sender']}→{m['receiver']}` `{m['action']}` — {m['status']} · {m.get('duration_ms', 0)}ms"
                )
    with tab_logs:
        logs, err = _attempt(lambda: client.audit_logs(limit=50))
        if err:
            st.error(err)
        else:
            for l in logs or []:
                st.markdown(
                    f"- `{l['action']}` on `{l['resource_type']}/{l['resource_id']}` by {l.get('role')} — {_fmt(l.get('timestamp'))}"
                )
    with tab_health:
        h, err = _attempt(client.health)
        if err:
            st.error(err)
        else:
            st.json(h)


# ==================================================================== ENTRY


def main() -> None:
    if not _ensure_client():
        return
    choice = sidebar()
    user = _user()
    top_nav()

    # The Agent Console is a separate top-nav view, not a sidebar page.
    if user.get("role") == "teacher" and st.session_state.get("view") == "agent_console":
        agent_console()
        _render_pending_task(_client())
        return

    if not choice:
        return
    if choice == "Dashboard":
        if user.get("role") == "teacher":
            teacher_dashboard()
        else:
            student_dashboard()
    elif choice == "Curriculum":
        teacher_curriculum()
    elif choice == "Class":
        teacher_class()
    elif choice == "Review Queue":
        teacher_review_queue()
    elif choice == "OBE Mapping":
        teacher_obe()
    elif choice == "Operations":
        operations_view()
    elif choice == "Study Plan":
        student_study_plan()
    elif choice == "Learn":
        student_learn()
    elif choice == "Quizzes":
        student_quizzes()
    elif choice == "My Progress":
        student_progress()
    elif choice == "Recommendations":
        student_recommendations()

    _render_pending_task(_client())


main()
