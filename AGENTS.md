# AGENTS.md

## Project Overview

AI Tutor is a local tutoring app using FastAPI, Streamlit, and Ollama. It provides chat answers, short conversation memory, document context upload, and YouTube recommendations.

## Architecture

- Backend: `api.py` exposes FastAPI routes including `/ask`, `/documents/upload`, `/documents/clear`, `/videos`, and `/health`.
- Model: `model.py` integrates with Ollama through `AITUTOR_OLLAMA_URL`, defaulting to `http://localhost:11434/api/generate`.
- Tutor logic: `logic.py` builds prompts, manages answer quality checks, and combines memory with retrieved context.
- Retrieval: `rag.py` reads local `docs/` content and session-uploaded `.txt` / `.pdf` documents using relative paths.
- Frontend: `streamlit_app.py` provides chat UI, document upload controls, metrics, and video recommendations.
- Launcher: `run_app.bat` activates `.venv`, starts FastAPI, then starts Streamlit.

## Setup

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

You can also run `setup.bat` on Windows.

## Run Commands

Backend:

```bat
python -m uvicorn api:app --reload
```

Frontend:

```bat
streamlit run streamlit_app.py
```

One-click launcher:

```bat
run_app.bat
```

## Known Behavior

- Ollama must be reachable for chat/model calls. Verify it at `http://127.0.0.1:11434/api/tags`.
- If Ollama is unreachable, the backend returns `503`, not `500`.
- Logs and tracebacks appear in the backend terminal.
- `AITUTOR_OLLAMA_URL` can point at another reachable Ollama endpoint such as Docker, WSL, or a remote host.

## Agent Guidelines

- Do not rewrite the entire project.
- Make minimal, targeted fixes.
- Preserve the FastAPI + Streamlit + Ollama architecture.
- Prefer debugging over rewriting.
- Keep launcher scripts portable and Windows-friendly.
- Ensure the app still runs end-to-end after changes.

## Debugging Rules

- Always check backend logs first.
- Verify Ollama at `http://127.0.0.1:11434/api/tags`.
- If the error is `503`, investigate the model server or `AITUTOR_OLLAMA_URL`.
- If the backend fails to start, check `.venv`, `python -m uvicorn api:app --reload`, and port `8000`.
- If Streamlit cannot reach the backend, check `AITUTOR_API_BASE_URL` and port `8000`.

