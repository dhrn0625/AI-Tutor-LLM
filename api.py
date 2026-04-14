from __future__ import annotations

import base64
import logging
import traceback
from contextlib import asynccontextmanager
from time import perf_counter
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from logic import clean_text, generate_answer, generate_structured_answer, normalize_level, summarize_text
from model import get_model
from rag import add_uploaded_document, clear_uploaded_documents, list_uploaded_documents
from youtube import recommend_videos

logger = logging.getLogger("ai_tutor.api")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

SESSION_MEMORY_LIMIT = 10
SESSION_MEMORY: dict[str, list[dict[str, object]]] = {}
SESSION_MEMORY_LOCK = Lock()


HOME_PAGE_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>AI Tutor API</title>
  </head>
  <body style="font-family: Arial, sans-serif; max-width: 720px; margin: 48px auto; line-height: 1.6;">
    <h1>AI Tutor API</h1>
    <p>The backend is running.</p>
    <p>Open <a href="/docs">/docs</a> for the interactive API page.</p>
    <p>Health check: <a href="/health">/health</a></p>
  </body>
</html>
""".strip()


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    level: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1, max_length=100)

    @field_validator("question", "level", "session_id")
    @classmethod
    def clean_value(cls, value: str) -> str:
        value = clean_text(value)
        if not value:
            raise ValueError("must not be empty")
        return value


class AskResponse(BaseModel):
    type: str
    level: str
    answer: str
    confidence: float
    latency_ms: int
    issues: str = ""
    verdict: str = "reliable"


class UploadDocumentItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    content_base64: str = Field(..., min_length=1)

    @field_validator("name", "content_base64")
    @classmethod
    def clean_value(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class UploadDocumentsRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100)
    files: list[UploadDocumentItem] = Field(..., min_length=1, max_length=10)

    @field_validator("session_id")
    @classmethod
    def clean_session(cls, value: str) -> str:
        value = clean_text(value)
        if not value:
            raise ValueError("must not be empty")
        return value


class DocumentsResponse(BaseModel):
    session_id: str
    documents: list[str]


class SessionRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100)

    @field_validator("session_id")
    @classmethod
    def clean_session(cls, value: str) -> str:
        value = clean_text(value)
        if not value:
            raise ValueError("must not be empty")
        return value


class VideosRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        value = clean_text(value)
        if not value:
            raise ValueError("must not be empty")
        return value


class VideoItem(BaseModel):
    title: str
    url: str


class VideosResponse(BaseModel):
    videos: list[VideoItem]


class StructuredResponse(BaseModel):
    type: str
    level: str
    answer: dict[str, str]


class SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=6000)

    @field_validator("text")
    @classmethod
    def clean_value(cls, value: str) -> str:
        value = clean_text(value)
        if not value:
            raise ValueError("must not be empty")
        return value


class SummarizeResponse(BaseModel):
    summary: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_model()
    yield


app = FastAPI(title="AI Tutor API", version="1.0.0", lifespan=lifespan)


def get_session_history(session_id: str) -> list[dict[str, object]]:
    with SESSION_MEMORY_LOCK:
        return [item.copy() for item in SESSION_MEMORY.get(session_id, [])][-SESSION_MEMORY_LIMIT:]


def append_session_message(session_id: str, role: str, content: str) -> None:
    with SESSION_MEMORY_LOCK:
        history = SESSION_MEMORY.setdefault(session_id, [])
        history.append({"role": role, "content": content})
        if len(history) > SESSION_MEMORY_LIMIT:
            del history[:-SESSION_MEMORY_LIMIT]


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return HOME_PAGE_HTML


@app.get("/health")
async def health() -> dict[str, str]:
    get_model()
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    try:
        level = normalize_level(request.level)
        history = get_session_history(request.session_id)
        logger.info("Handling /ask for session_id=%s level=%s", request.session_id, level)
        started = perf_counter()
        result = await run_in_threadpool(
            generate_answer,
            get_model(),
            request.question,
            level,
            history,
            request.session_id,
        )
        latency_ms = int((perf_counter() - started) * 1000)
        append_session_message(request.session_id, "user", request.question)
        append_session_message(request.session_id, "assistant", result["answer"])
        logger.info("Completed /ask for session_id=%s in %sms", request.session_id, latency_ms)
    except ValueError as exc:
        logger.warning("Validation error during /ask: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("Runtime error during /ask: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Unhandled error during /ask: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail="failed to generate answer") from exc
    return AskResponse(**result, latency_ms=latency_ms)


@app.post("/structured", response_model=StructuredResponse)
async def structured(request: AskRequest) -> StructuredResponse:
    try:
        level = normalize_level(request.level)
        result = await run_in_threadpool(
            generate_structured_answer,
            get_model(),
            request.question,
            level,
        )
    except ValueError as exc:
        logger.warning("Validation error during /structured: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("Runtime error during /structured: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Unhandled error during /structured: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail="failed to generate structured answer") from exc
    return StructuredResponse(**result)


@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(request: SummarizeRequest) -> SummarizeResponse:
    try:
        summary = await run_in_threadpool(summarize_text, get_model(), request.text)
    except RuntimeError as exc:
        logger.error("Runtime error during /summarize: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Unhandled error during /summarize: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail="failed to summarize text") from exc
    return SummarizeResponse(summary=summary)


@app.post("/documents/upload", response_model=DocumentsResponse)
async def upload_documents(request: UploadDocumentsRequest) -> DocumentsResponse:
    allowed_extensions = {".txt", ".pdf"}
    try:
        logger.info("Uploading %s document(s) for session_id=%s", len(request.files), request.session_id)
        for file in request.files:
            suffix = file.name.lower().rsplit(".", 1)
            extension = f".{suffix[-1]}" if len(suffix) > 1 else ""
            if extension not in allowed_extensions:
                raise ValueError(f"Unsupported file type for '{file.name}'.")
            content = base64.b64decode(file.content_base64.encode("utf-8"), validate=True)
            await run_in_threadpool(add_uploaded_document, request.session_id, file.name, content)
        documents = await run_in_threadpool(list_uploaded_documents, request.session_id)
    except ValueError as exc:
        logger.warning("Validation error during /documents/upload: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Unhandled error during /documents/upload: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail="failed to upload documents") from exc
    return DocumentsResponse(session_id=request.session_id, documents=documents)


@app.post("/documents/clear", response_model=DocumentsResponse)
async def clear_documents(request: SessionRequest) -> DocumentsResponse:
    try:
        await run_in_threadpool(clear_uploaded_documents, request.session_id)
    except Exception as exc:
        logger.error("Unhandled error during /documents/clear: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail="failed to clear documents") from exc
    return DocumentsResponse(session_id=request.session_id, documents=[])


@app.post("/videos", response_model=VideosResponse)
async def videos(request: VideosRequest) -> VideosResponse:
    try:
        videos = await run_in_threadpool(recommend_videos, request.query, 3)
    except Exception as exc:
        logger.error("Unhandled error during /videos: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail="failed to fetch videos") from exc
    return VideosResponse(videos=videos)
