"""PostPilot AI dashboard: login, sign up, new post requests, and post history."""

import os
from datetime import datetime

import requests
import streamlit as st

API_URL = os.getenv("POSTPILOT_API_URL", "http://localhost:8000")

# Keep in sync with the Tone / Length / PostStatus literals in backend/app/schemas.py.
TONES = [
    "professional",
    "conversational",
    "casual",
    "inspirational",
    "technical",
    "storytelling",
    "thought-leadership",
]
LENGTHS = {"short": "Short (~100 words)", "medium": "Medium (~200 words)", "long": "Long (~350 words)"}
STATUS_COLORS = {"pending": "orange", "generating": "blue", "completed": "green", "failed": "red"}
HISTORY_LIMIT = 50
# The agent pipeline makes several LLM calls; allow well beyond the backend's own timeout.
GENERATE_TIMEOUT_SECONDS = 600

st.set_page_config(page_title="PostPilot AI", page_icon="✈️")


def api(method: str, path: str, token: str | None = None, **kwargs) -> requests.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    kwargs.setdefault("timeout", 10)
    return requests.request(method, f"{API_URL}{path}", headers=headers, **kwargs)


def error_message(resp: requests.Response) -> str:
    try:
        detail = resp.json().get("detail")
    except ValueError:
        return f"Request failed ({resp.status_code})"
    if isinstance(detail, list):  # FastAPI validation errors
        return "; ".join(f"{e['loc'][-1]}: {e['msg']}" for e in detail)
    return detail or f"Request failed ({resp.status_code})"


def auth_page() -> None:
    st.title("✈️ PostPilot AI")
    login_tab, signup_tab = st.tabs(["Log in", "Sign up"])

    with login_tab:
        with st.form("login"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in")
        if submitted:
            try:
                resp = api("POST", "/api/auth/login", json={"email": email, "password": password})
            except requests.ConnectionError:
                st.error(f"Can't reach the API at {API_URL}. Is the backend running?")
                return
            if resp.ok:
                data = resp.json()
                st.session_state.token = data["access_token"]
                st.session_state.user = data["user"]
                st.rerun()
            else:
                st.error(error_message(resp))

    with signup_tab:
        with st.form("signup"):
            name = st.text_input("Name")
            email = st.text_input("Email")
            password = st.text_input("Password (min 8 characters)", type="password")
            submitted = st.form_submit_button("Create account")
        if submitted:
            try:
                resp = api(
                    "POST",
                    "/api/auth/register",
                    json={"name": name, "email": email, "password": password},
                )
            except requests.ConnectionError:
                st.error(f"Can't reach the API at {API_URL}. Is the backend running?")
                return
            if resp.ok:
                st.success("Account created. You can log in now.")
            else:
                st.error(error_message(resp))


def api_or_logout(method: str, path: str, **kwargs) -> requests.Response | None:
    """Authenticated call. Signs the user out on 401; returns None if the API is unreachable."""
    try:
        resp = api(method, path, token=st.session_state.token, **kwargs)
    except requests.ConnectionError:
        st.error(f"Can't reach the API at {API_URL}. Is the backend running?")
        return None
    if resp.status_code == 401:
        st.session_state.clear()
        st.rerun()
    return resp


def new_post_form() -> None:
    st.subheader("✍️ New post")
    with st.form("new_post", clear_on_submit=True):
        topic = st.text_area(
            "Topic",
            placeholder="e.g. What I learned shipping my first RAG system to production",
            max_chars=500,
        )
        audience = st.text_input(
            "Audience", placeholder="e.g. software engineers, recruiters, founders", max_chars=100
        )
        col_tone, col_length = st.columns(2)
        with col_tone:
            tone = st.selectbox("Tone", TONES, format_func=lambda t: t.replace("-", " ").title())
        with col_length:
            length = st.radio(
                "Length", list(LENGTHS), index=1, format_func=LENGTHS.get, horizontal=True
            )
        submitted = st.form_submit_button("Save post", type="primary")

    if submitted:
        resp = api_or_logout(
            "POST",
            "/api/posts",
            json={"topic": topic, "audience": audience, "tone": tone, "length": length},
        )
        if resp is None:
            return
        if resp.ok:
            st.success("Post saved. Click ✨ Generate on it below to run the agents.")
        else:
            st.error(error_message(resp))


def generate_post(post_id: int) -> None:
    with st.spinner("🔎 Researching → ✍️ Drafting → 🧐 Critiquing → ✨ Revising..."):
        try:
            resp = api_or_logout(
                "POST", f"/api/posts/{post_id}/generate", timeout=GENERATE_TIMEOUT_SECONDS
            )
        except requests.Timeout:
            st.error("Generation is taking too long. Refresh in a minute to see the result.")
            return
    if resp is None:
        return
    if resp.ok:
        st.session_state[f"show_{post_id}"] = True
        st.rerun()
    else:
        st.error(error_message(resp))


def show_latest_generation(post_id: int) -> None:
    resp = api_or_logout("GET", f"/api/posts/{post_id}/generations", params={"limit": 1})
    if resp is None:
        return
    if not resp.ok:
        st.error(error_message(resp))
        return
    items = resp.json()["items"]
    if not items:
        st.caption("No generations yet.")
        return
    gen = items[0]

    st.markdown("**📬 Final post**")
    st.code(gen["final_post"], language=None, wrap_lines=True)  # has a copy button

    critique = gen["critique"]
    cols = st.columns(3)
    cols[0].metric("Accuracy", f"{critique['accuracy_score']}/10")
    cols[1].metric("Engagement", f"{critique['engagement_score']}/10")
    cols[2].metric("Audience fit", f"{critique['audience_fit_score']}/10")

    draft_tab, research_tab, critique_tab = st.tabs(["✍️ First draft", "🔎 Research", "🧐 Critique"])
    with draft_tab:
        st.text(gen["draft"])
    with research_tab:
        research = gen["research_output"]
        st.write(research["summary"])
        for title, key in [
            ("Key facts", "key_facts"),
            ("Angles", "angles"),
            ("Audience insights", "audience_insights"),
            ("Pitfalls", "pitfalls"),
        ]:
            st.markdown(f"**{title}**\n" + "\n".join(f"- {item}" for item in research[key]))
    with critique_tab:
        for title, key in [("Strengths", "strengths"), ("Issues", "issues"), ("Suggestions", "suggestions")]:
            st.markdown(f"**{title}**\n" + "\n".join(f"- {item}" for item in critique[key]))


def post_history() -> None:
    resp = api_or_logout("GET", "/api/posts", params={"limit": HISTORY_LIMIT})
    if resp is None:
        return
    if not resp.ok:
        st.error(error_message(resp))
        return
    data = resp.json()

    st.subheader(f"🗂️ Your posts ({data['total']})")
    if not data["items"]:
        st.caption("No posts yet. Create your first one above.")
        return
    if data["total"] > HISTORY_LIMIT:
        st.caption(f"Showing your {HISTORY_LIMIT} most recent posts.")

    for post in data["items"]:
        with st.container(border=True):
            col_text, col_action = st.columns([6, 1])
            with col_text:
                st.markdown(f"**{post['topic']}**")
                created = datetime.fromisoformat(post["created_at"]).astimezone()
                color = STATUS_COLORS.get(post["status"], "gray")
                st.caption(
                    f":{color}[● {post['status']}] · 👥 {post['audience']} · "
                    f"🎨 {post['tone']} · 📏 {post['length']} · "
                    f"{created:%b %d, %Y %H:%M}"
                )
            with col_action:
                if post["status"] != "generating" and st.button(
                    "✨", key=f"generate_{post['id']}", help="Generate with the agents"
                ):
                    generate_post(post["id"])
                if st.button("🗑️", key=f"delete_{post['id']}", help="Delete this post"):
                    del_resp = api_or_logout("DELETE", f"/api/posts/{post['id']}")
                    if del_resp is None:
                        pass  # connection error already shown
                    elif del_resp.ok:
                        st.rerun()
                    else:
                        st.error(error_message(del_resp))
            if post["status"] == "completed" and st.toggle(
                "Show result", key=f"show_{post['id']}"
            ):
                show_latest_generation(post["id"])


def dashboard() -> None:
    user = st.session_state.user
    with st.sidebar:
        st.write(f"Signed in as **{user['name']}**")
        st.caption(user["email"])
        if st.button("Log out"):
            try:
                api("POST", "/api/auth/logout", token=st.session_state.token)
            except requests.ConnectionError:
                pass  # clear the local session regardless
            st.session_state.clear()
            st.rerun()

    st.title(f"Welcome, {user['name']} 👋")
    new_post_form()
    st.divider()
    post_history()


def session_is_valid() -> bool:
    """Confirm the stored token with the API so expired or revoked sessions are dropped."""
    token = st.session_state.get("token")
    if not token:
        return False
    try:
        resp = api("GET", "/api/auth/me", token=token)
    except requests.ConnectionError:
        return True  # keep the user signed in; the next call will surface the error
    if resp.ok:
        st.session_state.user = resp.json()
        return True
    st.session_state.clear()
    return False


if session_is_valid():
    dashboard()
else:
    auth_page()
