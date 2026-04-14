from __future__ import annotations

try:
    import psutil
except Exception:
    psutil = None


STATIC_METRICS = {
    "accuracy": 0.84,
    "f1_score": 0.82,
    "rouge_l": 0.41,
    "model": "llama3 (~8B via Ollama)",
}


def get_memory_usage_mb() -> float | str:
    if psutil is None:
        return "N/A"
    return psutil.Process().memory_info().rss / (1024 * 1024)


def get_metrics_snapshot(latency_ms: float = 0.0, confidence: float = 0.0) -> dict[str, float | str]:
    return {
        **STATIC_METRICS,
        "latency_ms": latency_ms,
        "confidence": confidence,
        "memory_mb": (
            round(get_memory_usage_mb(), 1)
            if isinstance(get_memory_usage_mb(), (int, float))
            else "N/A"
        ),
    }
