from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import Lock


DOCS_DIR = Path(__file__).resolve().parent / "docs"
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200

_SESSION_DOCUMENTS: dict[str, list[dict[str, object]]] = defaultdict(list)
_SESSION_DOCUMENTS_LOCK = Lock()


def _chunk_text(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, 0)
    return chunks


def _read_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_uploaded_file(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if suffix == ".txt":
        return content.decode("utf-8", errors="ignore")
    raise ValueError(f"Unsupported file type for '{filename}'. Only .txt and .pdf are allowed.")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9]{3,}", text.lower()))


def _score_chunk(query_terms: set[str], chunk: str) -> tuple[int, int]:
    chunk_terms = _tokenize(chunk)
    overlap = len(query_terms & chunk_terms)
    return overlap, len(chunk)


@lru_cache(maxsize=1)
def _load_index() -> list[dict[str, str]]:
    if not DOCS_DIR.exists():
        return []

    paths = [
        path
        for path in DOCS_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in {".txt", ".md", ".pdf"}
    ]
    if not paths:
        return []

    chunks: list[dict[str, str]] = []
    for path in paths:
        try:
            for chunk in _chunk_text(_read_file(path)):
                chunks.append({"source": path.name, "content": chunk})
        except Exception:
            continue

    return chunks


def add_uploaded_document(session_id: str, filename: str, content: bytes) -> str:
    text = _normalize_text(_read_uploaded_file(filename, content))
    if not text:
        raise ValueError(f"No readable text found in '{filename}'.")

    entry = {
        "name": filename,
        "content": text,
        "chunks": _chunk_text(text),
    }
    with _SESSION_DOCUMENTS_LOCK:
        documents = _SESSION_DOCUMENTS[session_id]
        documents[:] = [document for document in documents if document["name"] != filename]
        documents.append(entry)
    return filename


def list_uploaded_documents(session_id: str) -> list[str]:
    with _SESSION_DOCUMENTS_LOCK:
        return [str(document["name"]) for document in _SESSION_DOCUMENTS.get(session_id, [])]


def clear_uploaded_documents(session_id: str) -> None:
    with _SESSION_DOCUMENTS_LOCK:
        _SESSION_DOCUMENTS.pop(session_id, None)


def retrieve_uploaded_context(session_id: str, query: str, top_k: int = 3) -> list[str]:
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    with _SESSION_DOCUMENTS_LOCK:
        documents = list(_SESSION_DOCUMENTS.get(session_id, []))

    scored_chunks: list[tuple[tuple[int, int], str, str]] = []
    for document in documents:
        for chunk in document.get("chunks", []):
            score = _score_chunk(query_terms, str(chunk))
            if score[0] > 0:
                scored_chunks.append((score, str(document["name"]), str(chunk)))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    return [f"{name}: {chunk}" for _, name, chunk in scored_chunks[:top_k]]


def retrieve_context(query: str, top_k: int = 3) -> list[str]:
    query_terms = _tokenize(query)
    chunks = _load_index()
    if not chunks or not query_terms:
        return []

    scored_chunks: list[tuple[tuple[int, int], str]] = []
    for item in chunks:
        content = item["content"]
        score = _score_chunk(query_terms, content)
        if score[0] > 0:
            scored_chunks.append((score, f"{item['source']}: {content}"))

    scored_chunks.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in scored_chunks[:top_k]]


def retrieve_combined_context(session_id: str | None, query: str, top_k: int = 5) -> list[str]:
    """
    Retrieve the most relevant context chunks from built-in docs and uploaded docs.
    """
    chunks: list[str] = []
    chunks.extend(retrieve_context(query, max(1, top_k // 2)))
    if session_id:
        chunks.extend(retrieve_uploaded_context(session_id, query, max(1, top_k - len(chunks))))
    return chunks[:top_k]
