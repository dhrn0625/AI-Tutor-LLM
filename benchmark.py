from __future__ import annotations

from statistics import mean
from time import perf_counter

from logic import generate_answer, summarize_text
from model import get_model


QUESTION = "Explain Newton's second law with a simple example."
LEVEL = "basic"
TEXT = (
    "Newton's second law states that the acceleration of an object depends on the "
    "net force acting on it and its mass. A larger force produces more acceleration, "
    "while a larger mass produces less acceleration for the same force."
)


def timed_call(label: str, func, *args) -> tuple[object, float]:
    started = perf_counter()
    result = func(*args)
    elapsed = perf_counter() - started
    print(f"{label}: {elapsed:.3f}s")
    return result, elapsed


def main() -> None:
    model, load_elapsed = timed_call("model_load", get_model)

    _, ask_first = timed_call("ask_first", generate_answer, model, QUESTION, LEVEL)
    _, ask_second = timed_call("ask_second_cached", generate_answer, model, QUESTION, LEVEL)

    _, summarize_first = timed_call("summarize_first", summarize_text, model, TEXT)
    _, summarize_second = timed_call("summarize_second_cached", summarize_text, model, TEXT)

    average_hot = mean([ask_second, summarize_second])

    print()
    print("summary")
    print(f"model_load_seconds={load_elapsed:.3f}")
    print(f"ask_first_seconds={ask_first:.3f}")
    print(f"ask_cached_seconds={ask_second:.3f}")
    print(f"summarize_first_seconds={summarize_first:.3f}")
    print(f"summarize_cached_seconds={summarize_second:.3f}")
    print(f"average_cached_seconds={average_hot:.3f}")


if __name__ == "__main__":
    main()
