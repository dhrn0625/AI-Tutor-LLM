# AI Tutor LLM

## Project Overview

AI Tutor LLM is a local AI tutoring app powered by FastAPI, Streamlit, and an Ollama `llama3` model. It supports tutor-style chat, short conversation memory, document context upload for `.txt` and `.pdf` files, summarization, evaluation metrics, and YouTube video recommendations.

## Tech Stack

- **Backend:** FastAPI served with Uvicorn
- **Frontend:** Streamlit
- **Model runtime:** Ollama at `http://127.0.0.1:11434` by default
- **Document parsing:** `pypdf`
- **Evaluation helpers:** `psutil` and local evaluation scripts

## Features

- Prompt-based query classification into `concept`, `problem`, or `theory`
- Step-by-step tutor answers
- Text summarization
- Adaptive answer depth for `basic`, `intermediate`, and `advanced`
- Single shared model instance for lower memory use and better latency
- Upload `.txt` and `.pdf` documents as in-memory context
- Recommend relevant YouTube videos for user questions

## Project Structure

- `model.py`: loads the model once and exposes a shared generator
- `logic.py`: classification, prompt building, answer generation, summarization
- `api.py`: FastAPI app and HTTP routes
- `streamlit_app.py`: simple frontend connected to the FastAPI backend
- `rag.py`: local and uploaded document retrieval
- `run_app.bat`: Windows one-click launcher
- `setup.bat`: Windows setup helper

## Requirements

- Python 3.10+
- CPU environment with under 8 GB RAM
- Ollama running with the configured model available

## Setup Instructions

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

On Windows, you can also run:

```bat
setup.bat
```

## Run Instructions

Make sure Ollama is running locally at `http://127.0.0.1:11434` with the `llama3` model available.

Run the FastAPI backend manually:

```bash
python -m uvicorn api:app --reload
```

Run the Streamlit frontend in a second terminal:

```bash
streamlit run streamlit_app.py
```

Or launch both services on Windows:

```bat
run_app.bat
```

## Benchmark

Run a small local benchmark:

```bash
.venv\Scripts\python.exe benchmark.py
```

## Evaluation

Run a simple evaluation script:

```bash
.venv\Scripts\python.exe evaluate.py
```

It reports:
- classification accuracy on a small dummy dataset
- average ROUGE-L for summarization
- average and max latency per request

## API

### `GET /health`

Response:

```json
{
  "status": "ok"
}
```

### `POST /ask`

Request:

```json
{
  "question": "What is Newton's second law?",
  "level": "basic",
  "session_id": "demo"
}
```

Response:

```json
{
  "type": "concept",
  "level": "basic",
  "answer": "1. Newton's second law explains how force affects motion...",
  "confidence": 0.82,
  "latency_ms": 1200,
  "issues": "",
  "verdict": "reliable"
}
```

### `POST /summarize`

Request:

```json
{
  "text": "Long text to summarize..."
}
```

Response:

```json
{
  "summary": "Short summary..."
}
```

## Notes

- The service keeps one model instance in memory for all requests.
- Classification is prompt-based and does not require training.
- Responses are generated on CPU and tuned to stay lightweight.
- Inference runs in FastAPI's threadpool so API routes stay responsive while the CPU model works.
- If Ollama is unavailable, model endpoints return `503 Service Unavailable` rather than a generic `500`.

## Troubleshooting

- **Backend will not start:** activate `.venv`, then run `python -m uvicorn api:app --reload` and check the terminal output.
- **Streamlit cannot reach backend:** confirm FastAPI is running at `http://127.0.0.1:8000` or set `AITUTOR_API_BASE_URL`.
- **Chat returns 503:** Ollama is unavailable from this environment. Check `http://127.0.0.1:11434/api/tags`, start Ollama, or set `AITUTOR_OLLAMA_URL` to the reachable `/api/generate` endpoint.
- **Launcher reports dependency errors:** run `setup.bat` again, then retry `run_app.bat`.
