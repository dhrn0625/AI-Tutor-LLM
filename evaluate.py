from __future__ import annotations

from statistics import mean
from time import perf_counter

from logic import classify_query, summarize_text
from model import get_model


CLASSIFICATION_DATASET = [
    {"question": "What is a cell in biology?", "label": "concept"},
    {"question": "Solve 3x - 4 = 11", "label": "problem"},
    {"question": "Explain quantum theory", "label": "theory"},
    {"question": "What does gravity mean?", "label": "concept"},
    {"question": "Find the area of a circle with radius 7", "label": "problem"},
    {"question": "Describe the theory of evolution", "label": "theory"},
]

SUMMARIZATION_DATASET = [
    {
        "text": (
            "Plants make food through photosynthesis. They use sunlight, water, "
            "and carbon dioxide to produce glucose and oxygen. This process helps "
            "plants grow and also releases oxygen into the air."
        ),
        "reference": (
            "Photosynthesis is the process by which plants use sunlight, water, "
            "and carbon dioxide to make food and release oxygen."
        ),
    },
    {
        "text": (
            "The water cycle includes evaporation, condensation, and precipitation. "
            "Water evaporates from oceans and lakes, forms clouds through condensation, "
            "and returns to Earth as rain or snow."
        ),
        "reference": (
            "The water cycle moves water through evaporation, condensation, and "
            "precipitation as it circulates between Earth and the atmosphere."
        ),
    },
]


def tokenize(text: str) -> list[str]:
    return text.lower().split()


def lcs_length(a: list[str], b: list[str]) -> int:
    rows = len(a) + 1
    cols = len(b) + 1
    dp = [[0] * cols for _ in range(rows)]

    for i in range(1, rows):
        for j in range(1, cols):
            if a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    return dp[-1][-1]


def rouge_l_score(reference: str, prediction: str) -> float:
    ref_tokens = tokenize(reference)
    pred_tokens = tokenize(prediction)
    if not ref_tokens or not pred_tokens:
        return 0.0

    lcs = lcs_length(ref_tokens, pred_tokens)
    precision = lcs / len(pred_tokens)
    recall = lcs / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


def timed_call(func, *args):
    started = perf_counter()
    result = func(*args)
    elapsed = perf_counter() - started
    return result, elapsed


def evaluate_classification(model) -> None:
    correct = 0
    latencies: list[float] = []

    for item in CLASSIFICATION_DATASET:
        prediction, elapsed = timed_call(classify_query, model, item["question"])
        latencies.append(elapsed)
        if prediction == item["label"]:
            correct += 1

    accuracy = correct / len(CLASSIFICATION_DATASET)
    print("classification")
    print(f"accuracy={accuracy:.3f}")
    print(f"avg_latency_seconds={mean(latencies):.3f}")
    print(f"max_latency_seconds={max(latencies):.3f}")


def evaluate_summarization(model) -> None:
    scores: list[float] = []
    latencies: list[float] = []

    for item in SUMMARIZATION_DATASET:
        summary, elapsed = timed_call(summarize_text, model, item["text"])
        latencies.append(elapsed)
        scores.append(rouge_l_score(item["reference"], summary))

    print()
    print("summarization")
    print(f"rouge_l={mean(scores):.3f}")
    print(f"avg_latency_seconds={mean(latencies):.3f}")
    print(f"max_latency_seconds={max(latencies):.3f}")


def main() -> None:
    model, load_elapsed = timed_call(get_model)
    print(f"model_load_seconds={load_elapsed:.3f}")
    print()
    evaluate_classification(model)
    evaluate_summarization(model)


if __name__ == "__main__":
    main()
