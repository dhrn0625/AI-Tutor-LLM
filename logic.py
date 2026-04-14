from __future__ import annotations

import json
import re
from typing import Literal

from model import TutorModel, NUM_PREDICT
from rag import retrieve_context, retrieve_uploaded_context
from verifier import assess_answer, extract_equations, verify_equations


QueryType = Literal["concept", "problem", "theory"]
Level = Literal["basic", "intermediate", "advanced"]

VALID_LEVELS: set[str] = {"basic", "intermediate", "advanced"}
MEMORY_LIMIT = 10
STRUCTURED_FIELDS = ("definition", "formula", "explanation", "example", "summary")
ADVANCED_KEYWORDS = (
    "derive",
    "prove",
    "formal",
    "rigorous",
    "analyze",
    "optimize",
    "theory",
    "implementation",
)

CHAT_PROMPT = """
You are an expert tutor for graduate-level students across multiple disciplines.

Your priority:
1. correctness
2. clarity
3. depth

You are having a conversation with a student.

Guidelines:
- Identify the correct concept and domain first
- Do NOT invent definitions or reinterpret terms incorrectly
- Expand abbreviations correctly when standard meaning is known
- Example: NeRF means Neural Radiance Fields
- Answer naturally and clearly
- Use previous conversation for context
- Adapt to {depth}
- Use the domain context when helpful: {domain}
- Do not oversimplify advanced queries
- Prefer correctness over simplification
- Use equations, derivations, algorithms, or technical detail when the topic needs them
- Prefer standard textbook explanations
- If uncertain, give a safe conceptual explanation rather than speculative detail

Math formatting rules:
- If the explanation involves mathematics, ALWAYS use LaTeX
- Inline math must use $...$
- Important equations must use $$...$$
- NEVER write plain text equations like "F = ma"
- Use proper notation for vectors, subscripts, and symbols
- NEVER invent formulas
- If unsure, explain conceptually instead of fake math

Examples:
- $$ \\vec{{F}}_{{AB}} = -\\vec{{F}}_{{BA}} $$
- $$ \\vec{{p}} = m \\vec{{v}} $$
- $$ \\sum_i \\vec{{p}}_i = \\text{{constant}} $$

IMPORTANT:
- Ensure your response is COMPLETE
- Do NOT end mid-sentence or mid-explanation
- If the explanation is long, summarize and conclude clearly
- Prefer finishing the idea over continuing indefinitely
- In advanced mode, prefer formal mathematical expressions where appropriate
- In advanced mode, prefer equations over verbal descriptions

Use the following context if relevant:
{retrieved_docs}

Conversation:
{context}

Student: {query}
Tutor:
""".strip()

STRUCTURED_PROMPT = """
You are an expert tutor.

Explain the question at a {level} level.

Level guidelines:
- basic: simple explanation, easy words, short sentences
- intermediate: moderate detail
- advanced: deeper explanation with precise terms

Return ONLY valid JSON in this format:

{{
  "definition": "...",
  "formula": "...",
  "explanation": "...",
  "example": "...",
  "summary": "..."
}}

Rules:
- Always provide a real answer
- If a formula exists, include it
- If no formula exists, write "Not applicable"
- Do not include any extra text outside JSON

Question: {query}
""".strip()

SUMMARY_PROMPT = """
Summarize the following text in a concise and clear way.

Text:
{text}

Summary:
""".strip()


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_latex(text: str) -> str:
    text = text.replace("\\\\(", "\\(").replace("\\\\)", "\\)")
    text = text.replace("\\\\[", "\\[").replace("\\\\]", "\\]")
    text = re.sub(r"\\\((.*?)\\\)", r"$\1$", text, flags=re.DOTALL)
    text = re.sub(r"\\\[(.*?)\\\]", r"$$\1$$", text, flags=re.DOTALL)
    text = re.sub(r"\$\$\s*\$\$", "", text)
    if text.count("$$") % 2 != 0:
        text = text.rstrip("$")
    if re.sub(r"\$\$.*?\$\$", "", text, flags=re.DOTALL).count("$") % 2 != 0:
        text = text.rstrip("$")

    return text


def normalize_level(level: str) -> Level:
    level = clean_text(level).lower()
    if level not in VALID_LEVELS:
        raise ValueError("level must be one of: basic, intermediate, advanced")
    return level  # type: ignore[return-value]


def classify_query(_: TutorModel, question: str) -> QueryType:
    query = clean_text(question).lower()
    if any(word in query for word in ("what", "explain", "define")):
        return "concept"
    if any(word in query for word in ("solve", "calculate")):
        return "problem"
    if any(word in query for word in ("derive", "prove")):
        return "theory"
    return "concept"


def infer_depth(level: Level, question: str) -> Level:
    query = clean_text(question).lower()
    if any(keyword in query for keyword in ADVANCED_KEYWORDS):
        return "advanced"
    return level


def infer_domain(question: str) -> str:
    query = clean_text(question).lower()

    if any(term in query for term in ("matrix", "integral", "derivative", "equation", "theorem", "algebra", "calculus")):
        return "mathematics"
    if any(term in query for term in ("force", "energy", "quantum", "velocity", "acceleration", "relativity", "thermodynamics")):
        return "physics"
    if any(term in query for term in ("algorithm", "runtime", "complexity", "code", "python", "database", "compiler", "implementation")):
        return "computer science"
    if any(term in query for term in ("probability", "regression", "likelihood", "bayes", "variance", "distribution", "machine learning", "statistics")):
        return "statistics / machine learning"
    if any(term in query for term in ("proof", "derive", "axiom", "logic", "theory")):
        return "theoretical topic"
    return "general academic"


def format_memory(history: list[dict[str, object]] | None) -> str:
    if not history:
        return "No previous conversation."

    lines: list[str] = []
    for item in history[-MEMORY_LIMIT:]:
        role = clean_text(str(item.get("role", ""))).lower()
        content = clean_text(str(item.get("content", "")))
        if not content:
            continue
        if role == "assistant":
            lines.append(f"Tutor: {content}")
        else:
            lines.append(f"User: {content}")
    if not lines:
        return "No previous conversation."
    return "\n".join(lines)


def build_chat_prompt(
    question: str,
    level: Level,
    history: list[dict[str, object]] | None = None,
    retrieved_docs: list[str] | None = None,
) -> str:
    depth = infer_depth(level, question)
    docs = "\n\n".join(f"- {doc}" for doc in (retrieved_docs or [])) or "No retrieved context."
    return CHAT_PROMPT.format(
        depth=depth,
        domain=infer_domain(question),
        retrieved_docs=docs,
        context=format_memory(history),
        query=clean_text(question),
    )


def build_structured_prompt(question: str, level: Level) -> str:
    return STRUCTURED_PROMPT.format(level=level, query=clean_text(question))


def is_incomplete(text: str) -> bool:
    return bool(text.strip()) and not text.strip().endswith((".", "!", "?"))


def _clean_chat_answer(text: str) -> str:
    text = re.sub(r"^\s*Tutor:\s*", "", text.strip(), flags=re.IGNORECASE)
    return normalize_latex(text)


def _extract_json_substring(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_json(text: str) -> dict[str, str] | None:
    for candidate in (text.strip(), _extract_json_substring(text).strip()):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return {str(key): clean_text(str(value)) for key, value in data.items()}
    return None


def _finalize_structured_answer(data: dict[str, str], question: str) -> dict[str, str]:
    question = clean_text(question)
    answer = {field: clean_text(data.get(field, "")) for field in STRUCTURED_FIELDS}
    if not answer["definition"]:
        answer["definition"] = f"{question} is an important concept."
    if not answer["formula"]:
        answer["formula"] = "Not applicable"
    if not answer["explanation"]:
        answer["explanation"] = f"{question} can be explained using its main idea and context."
    if not answer["example"]:
        answer["example"] = f"A simple example can make {question} easier to understand."
    if not answer["summary"]:
        answer["summary"] = f"In summary, {question} becomes clearer through explanation and example."
    return answer


def _continue_prompt(level: Level, history: list[dict[str, object]] | None, question: str, partial: str) -> str:
    del level, history, question
    return f"""
Continue this explanation and finish it clearly. Do not repeat.

{_clean_chat_answer(partial)}
""".strip()


def generate_answer(
    model: TutorModel,
    question: str,
    level: Level,
    history: list[dict[str, object]] | None = None,
    session_id: str | None = None,
) -> dict[str, str]:
    question = clean_text(question)
    query_type = classify_query(model, question)
    retrieved_docs = retrieve_context(question)
    if session_id:
        retrieved_docs.extend(retrieve_uploaded_context(session_id, question))
    answer = _clean_chat_answer(
        model.generate(build_chat_prompt(question, level, history, retrieved_docs), max_new_tokens=NUM_PREDICT)
    )

    attempts = 0
    while is_incomplete(answer) and attempts < 2:
        continuation = _clean_chat_answer(
            model.generate(_continue_prompt(level, history, question, answer), max_new_tokens=NUM_PREDICT // 2)
        )
        if continuation:
            answer = f"{answer} {continuation}".strip()
        attempts += 1

    confidence_data = assess_answer(model, question, answer)
    equation_check = verify_equations(model, extract_equations(answer))

    if confidence_data["verdict"] == "uncertain" or not equation_check["valid"]:
        strict_prompt = (
            f"{build_chat_prompt(question, level, history, retrieved_docs)}\n\n"
            "Provide a correct, standard explanation. Avoid speculation."
        )
        if not equation_check["valid"]:
            strict_prompt += " Use only correct and standard equations."

        answer = _clean_chat_answer(model.generate(strict_prompt, max_new_tokens=NUM_PREDICT))
        if is_incomplete(answer):
            continuation = _clean_chat_answer(
                model.generate(_continue_prompt(level, history, question, answer), max_new_tokens=NUM_PREDICT // 2)
            )
            if continuation:
                answer = f"{answer} {continuation}".strip()

        confidence_data = assess_answer(model, question, answer)
        equation_check = verify_equations(model, extract_equations(answer))

    return {
        "type": query_type,
        "level": level,
        "answer": answer,
        "confidence": round(float(confidence_data["confidence"]), 2),
        "issues": ", ".join(confidence_data["issues"]),
        "verdict": str(confidence_data["verdict"]),
    }


def generate_structured_answer(model: TutorModel, question: str, level: Level) -> dict[str, object]:
    question = clean_text(question)
    query_type = classify_query(model, question)
    prompt = build_structured_prompt(question, level)
    raw = model.generate(prompt, max_new_tokens=NUM_PREDICT)
    parsed = _parse_json(raw)
    if parsed is None:
        raw = model.generate(prompt, max_new_tokens=NUM_PREDICT)
        parsed = _parse_json(raw)
    if parsed is None:
        parsed = _parse_json(_extract_json_substring(raw)) or {}
    return {"type": query_type, "level": level, "answer": _finalize_structured_answer(parsed, question)}


def summarize_text(model: TutorModel, text: str) -> str:
    return model.generate(SUMMARY_PROMPT.format(text=clean_text(text)), max_new_tokens=NUM_PREDICT // 2)
