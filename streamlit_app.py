from __future__ import annotations

import base64
import json
import os
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st
import streamlit.components.v1 as components

from evaluation import get_metrics_snapshot


API_BASE_URL = os.environ.get("AITUTOR_API_BASE_URL", "http://127.0.0.1:8000")
LEVEL_OPTIONS = ("basic", "intermediate", "advanced")


def post_json(path: str, payload: dict, timeout: int = 60) -> dict:
    request = Request(
        url=f"{API_BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") or exc.reason
        raise RuntimeError(f"Backend error: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(
            f"Could not reach FastAPI backend at {API_BASE_URL}. Start the API first."
        ) from exc


def create_chat() -> str:
    chat_id = str(uuid.uuid4())
    st.session_state.chats[chat_id] = {
        "title": "New Chat",
        "level": "basic",
        "messages": [],
        "documents": [],
        "videos": [],
    }
    st.session_state.chat_order.insert(0, chat_id)
    st.session_state.current_chat_id = chat_id
    return chat_id


def init_state() -> None:
    if "chats" not in st.session_state:
        st.session_state.chats = {}
    if "chat_order" not in st.session_state:
        st.session_state.chat_order = []
    if "current_chat_id" not in st.session_state:
        create_chat()
    elif st.session_state.current_chat_id not in st.session_state.chats:
        create_chat()
    for chat in st.session_state.chats.values():
        chat.setdefault("documents", [])
        chat.setdefault("videos", [])


def get_current_chat() -> dict:
    return st.session_state.chats[st.session_state.current_chat_id]


def set_chat_title(chat: dict, question: str) -> None:
    if chat["title"] == "New Chat":
        short = question.strip()
        chat["title"] = short[:30] + ("..." if len(short) > 30 else "")


def get_last_user_question(chat: dict) -> str:
    for message in reversed(chat["messages"]):
        if message["role"] == "user":
            return str(message["content"])
    return ""


def update_chat_documents(chat: dict, documents: list[str]) -> None:
    chat["documents"] = documents


def upload_documents(chat_id: str, files: list[object]) -> list[str]:
    payload = {
        "session_id": chat_id,
        "files": [
            {
                "name": file.name,
                "content_base64": base64.b64encode(file.getvalue()).decode("utf-8"),
            }
            for file in files
        ],
    }
    response = post_json("/documents/upload", payload)
    return list(response.get("documents", []))


def clear_documents(chat_id: str) -> list[str]:
    response = post_json("/documents/clear", {"session_id": chat_id})
    return list(response.get("documents", []))


def fetch_videos(query: str) -> list[dict[str, str]]:
    response = post_json("/videos", {"query": query})
    return list(response.get("videos", []))


def render_sidebar() -> None:
    with st.sidebar:
        st.title("Chats")
        if st.button("New Chat", use_container_width=True, type="primary"):
            create_chat()
            st.rerun()

        for chat_id in st.session_state.chat_order:
            chat = st.session_state.chats[chat_id]
            is_current = chat_id == st.session_state.current_chat_id
            label = chat["title"] if chat["title"] else "New Chat"
            if st.button(
                label,
                key=f"chat_{chat_id}",
                use_container_width=True,
                disabled=is_current,
            ):
                st.session_state.current_chat_id = chat_id
                st.rerun()

        show_metrics = st.checkbox("Show Metrics", True)
        if show_metrics:
            metrics = get_metrics_snapshot(
                latency_ms=st.session_state.get("latest_latency_ms", 0),
                confidence=st.session_state.get("latest_confidence", 0.0),
            )
            st.divider()
            st.subheader("Evaluation Metrics")
            st.write(f"Accuracy: {format_metric(metrics['accuracy'], multiplier=100, suffix='%')}")
            st.write(f"F1-score: {format_metric(metrics['f1_score'])}")
            st.write(f"ROUGE-L: {format_metric(metrics['rouge_l'])}")
            st.write(f"Latency: {format_metric(metrics['latency_ms'], decimals=0, suffix=' ms')}")
            st.write(f"Memory: {format_metric(metrics['memory_mb'], suffix=' MB')}")
            st.write(f"Model: {format_metric(metrics['model'])}")

        st.divider()
        st.subheader("Documents")
        current_chat = get_current_chat()
        uploaded_files = st.file_uploader(
            "Upload .txt or .pdf",
            type=["txt", "pdf"],
            accept_multiple_files=True,
            key=f"documents_{st.session_state.current_chat_id}",
        )
        if uploaded_files and st.button("Add Documents", use_container_width=True):
            try:
                documents = upload_documents(st.session_state.current_chat_id, uploaded_files)
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                update_chat_documents(current_chat, documents)
                st.rerun()

        if current_chat["documents"]:
            st.caption("Active files")
            for name in current_chat["documents"]:
                st.write(f"- {name}")

        if st.button("Clear Documents", use_container_width=True):
            try:
                documents = clear_documents(st.session_state.current_chat_id)
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                update_chat_documents(current_chat, documents)
                st.rerun()


def render_messages(chat: dict) -> None:
    for message in chat["messages"]:
        with st.chat_message(message["role"]):
            render_message_content(message["content"], message["role"])
            render_message_meta(message)


def format_metric(value: object, *, decimals: int = 2, multiplier: float = 1.0, suffix: str = "") -> str:
    if isinstance(value, (int, float)):
        scaled = value * multiplier
        if decimals == 0:
            return f"{scaled:.0f}{suffix}"
        return f"{scaled:.{decimals}f}{suffix}"
    return f"{value}"


def normalize_math_delimiters(text: str) -> str:
    text = re.sub(r"\\\[(.*?)\\\]", r"$$\1$$", text, flags=re.DOTALL)
    text = re.sub(r"\\\((.*?)\\\)", r"$\1$", text, flags=re.DOTALL)
    if text.count("$$") % 2 != 0:
        text = text.replace("$$", "", 1)
    if text.count("$") % 2 != 0:
        text += "$"
    return text


def render_message_content(content: str, role: str) -> None:
    if role == "user":
        st.markdown(content, unsafe_allow_html=True)
        return

    st.markdown(normalize_math_delimiters(content), unsafe_allow_html=True)


def render_message_meta(message: dict) -> None:
    if message["role"] != "assistant":
        return

    parts: list[str] = []
    if "confidence" in message:
        parts.append(f"Confidence: {float(message['confidence']):.2f}")
    if "latency_ms" in message:
        parts.append(f"Latency: {int(message['latency_ms'])} ms")
    if parts:
        st.caption(" | ".join(parts))
    if message.get("issues"):
        st.caption(f"Issues: {message['issues']}")


def render_video_recommendations(chat: dict) -> None:
    st.divider()
    st.subheader("Recommended Videos")
    if not chat["videos"]:
        st.caption("Ask a question to see related YouTube videos.")
        return

    for video in chat["videos"]:
        title = str(video.get("title", "Untitled video"))
        url = str(video.get("url", ""))
        if url:
            st.markdown(f"- [{title}]({url})")


def scroll_to_latest() -> None:
    components.html(
        """
        <script>
        const timer = setTimeout(() => {
          window.parent.scrollTo(0, document.body.scrollHeight);
        }, 100);
        </script>
        """,
        height=0,
    )


def main() -> None:
    st.set_page_config(page_title="AI Tutor", page_icon="AI", layout="wide")
    init_state()
    render_sidebar()

    chat = get_current_chat()

    st.title("AI Tutor")
    st.caption("Chat with your tutor across multiple saved conversations.")

    chat["level"] = st.selectbox(
        "Level",
        LEVEL_OPTIONS,
        index=LEVEL_OPTIONS.index(chat["level"]),
        key=f"level_{st.session_state.current_chat_id}",
    )

    render_messages(chat)
    videos_placeholder = st.empty()
    with videos_placeholder.container():
        render_video_recommendations(chat)

    last_user_question = get_last_user_question(chat)
    if st.button(
        "Recommend Videos",
        use_container_width=False,
        disabled=not last_user_question,
    ):
        try:
            chat["videos"] = fetch_videos(last_user_question)
        except RuntimeError as exc:
            st.error(str(exc))
        else:
            st.rerun()

    question = st.chat_input("Ask a question...")
    if question:
        question = question.strip()
        if not question:
            st.warning("Please enter a question.")
            return

        chat["messages"].append({"role": "user", "content": question})
        set_chat_title(chat, question)

        with st.chat_message("user"):
            render_message_content(question, "user")

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    result = post_json(
                        "/ask",
                        {
                            "question": question,
                            "level": chat["level"],
                            "session_id": st.session_state.current_chat_id,
                        },
                    )
                    answer = result["answer"]
                    confidence = float(result.get("confidence", 0.0))
                    latency_ms = int(result.get("latency_ms", 0))
                    issues = result.get("issues", "")
                except RuntimeError as exc:
                    answer = str(exc)
                    confidence = 0.0
                    latency_ms = 0
                    issues = ""
                    videos = []
                    st.error(answer)
                else:
                    render_message_content(answer, "assistant")
                    render_message_meta(
                        {
                            "role": "assistant",
                            "confidence": confidence,
                            "latency_ms": latency_ms,
                            "issues": issues,
                        }
                    )
                    try:
                        videos = fetch_videos(question)
                    except RuntimeError:
                        videos = []

        st.session_state.latest_confidence = confidence
        st.session_state.latest_latency_ms = latency_ms
        chat["videos"] = videos
        chat["messages"].append(
            {
                "role": "assistant",
                "content": answer,
                "confidence": confidence,
                "latency_ms": latency_ms,
                "issues": issues,
            }
        )
        with videos_placeholder.container():
            render_video_recommendations(chat)
        scroll_to_latest()


if __name__ == "__main__":
    main()
