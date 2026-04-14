from __future__ import annotations

import json
import re

from model import TutorModel


def _extract_json_substring(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_json(text: str) -> dict | None:
    for candidate in (text.strip(), _extract_json_substring(text).strip()):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def assess_answer(model: TutorModel, question: str, answer: str) -> dict[str, object]:
    prompt = f"""
Evaluate the following answer:
- Is it factually correct?
- Does it contain hallucinations or incorrect claims?

Return:
{{
  "confidence": 0-1,
  "issues": ["..."],
  "verdict": "reliable" | "uncertain"
}}

Question: {question}
Answer: {answer}
""".strip()

    data = _parse_json(model.generate(prompt, max_new_tokens=250)) or {}
    confidence = data.get("confidence", 0.5)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.5

    issues = data.get("issues", [])
    if not isinstance(issues, list):
        issues = [str(issues)]

    verdict = str(data.get("verdict", "uncertain")).strip().lower()
    if verdict not in {"reliable", "uncertain"}:
        verdict = "uncertain"

    return {
        "confidence": max(0.0, min(confidence, 1.0)),
        "issues": [str(item) for item in issues],
        "verdict": verdict,
    }


def extract_equations(text: str) -> list[str]:
    matches = re.findall(r"\$\$(.*?)\$\$|\$(.*?)\$", text, flags=re.DOTALL)
    results: list[str] = []
    for display, inline in matches:
        value = (display or inline).strip()
        if value:
            results.append(value)
    return results


def verify_equations(model: TutorModel, equations: list[str]) -> dict[str, object]:
    if not equations:
        return {"valid": True, "corrections": []}

    prompt = f"""
Check if the following equations are valid and standard:
{chr(10).join(equations)}

Return:
{{
  "valid": "valid" | "invalid",
  "corrections": ["..."]
}}
""".strip()

    data = _parse_json(model.generate(prompt, max_new_tokens=200)) or {}
    valid = str(data.get("valid", "valid")).strip().lower() == "valid"
    corrections = data.get("corrections", [])
    if not isinstance(corrections, list):
        corrections = [str(corrections)]
    return {"valid": valid, "corrections": [str(item) for item in corrections]}
