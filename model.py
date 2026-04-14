from __future__ import annotations

import json
import os
from collections import OrderedDict
from functools import lru_cache
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OLLAMA_URL = os.environ.get("AITUTOR_OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = os.environ.get("AITUTOR_MODEL_NAME", "llama3")
TEMPERATURE = float(os.environ.get("AITUTOR_TEMPERATURE", "0.7"))
TOP_P = float(os.environ.get("AITUTOR_TOP_P", "0.9"))
NUM_PREDICT = int(os.environ.get("AITUTOR_NUM_PREDICT", "800"))
NUM_CTX = int(os.environ.get("AITUTOR_NUM_CTX", "4096"))
CACHE_SIZE = 128


def generate_response(prompt: str, *, stream: bool = False, num_predict: int = NUM_PREDICT) -> str:
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": stream,
        "options": {
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "num_predict": num_predict,
            "num_ctx": NUM_CTX,
        },
    }
    request = Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=180) as response:
            if stream:
                chunks: list[str] = []
                for line in response:
                    if not line.strip():
                        continue
                    data = json.loads(line.decode("utf-8"))
                    chunks.append(data.get("response", ""))
                return "".join(chunks).strip()
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") or exc.reason
        raise RuntimeError(f"Ollama request failed: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(
            "Could not reach Ollama at "
            f"{OLLAMA_URL}. Ensure Ollama is running in the same network environment. "
            "If Ollama is running in Docker, WSL, or another host, set AITUTOR_OLLAMA_URL "
            "to the reachable /api/generate endpoint, for example "
            "http://localhost:11434/api/generate, "
            "http://host.docker.internal:11434/api/generate, or "
            "http://<WSL-bridge-IP>:11434/api/generate."
        ) from exc

    return data.get("response", "").strip()


class TutorModel:
    def __init__(self) -> None:
        self.lock = Lock()
        self.cache: OrderedDict[tuple[str, int], str] = OrderedDict()

    def generate(self, prompt: str, *, max_new_tokens: int = NUM_PREDICT) -> str:
        cache_key = (prompt, max_new_tokens)
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.cache.move_to_end(cache_key)
            return cached

        with self.lock:
            result = generate_response(prompt, num_predict=max_new_tokens)

        self.cache[cache_key] = result
        self.cache.move_to_end(cache_key)
        if len(self.cache) > CACHE_SIZE:
            self.cache.popitem(last=False)
        return result


@lru_cache(maxsize=1)
def get_model() -> TutorModel:
    return TutorModel()
