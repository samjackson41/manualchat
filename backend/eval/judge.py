"""LLM-as-judge — rubric-based scoring of one markdown answer.

The judge reads the case, the agent's answer, and the reference, then returns a
structured `Judgement`. Two habits keep it honest:

    1. the reason comes before the score, which reduces rationalizing;
    2. the return is structured, so the runner aggregates without parsing prose.

Citation precision is NOT judged by the model. It is computed in code from the
`[Page N]` markers, because a count is exact and a model is not.

The judge model stays distinct from the model under test (DECISIONS E1), so
self-preference bias stays low.

This is a LIBRARY: importing it makes no LLM or network call. `judge()` calls
the LLM only when it runs.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from pydantic import BaseModel, Field

from backend import llm
from backend.config import get_settings
from backend.eval.dataset import EvalCase

# Rubrics per category. Keep them tight — the rubric is the spec.
RUBRICS: dict[str, str] = {
    "spec": (
        "Score how correct the specification value is. 1.0 = the key value or "
        "values match the reference with the correct unit and qualifier (model "
        "range, U.S. versus non-U.S., torque units), and every page the answer "
        "cites is inside the allowed answer pages. A wrong number, unit, or "
        "qualifier scores low. A correct value on a wrong or missing page is "
        "penalized: citation precision is part of the score. Trust the reference "
        "over the agent."
    ),
    "procedure": (
        "Score how correct the procedure is. 1.0 = the steps match the reference "
        "in substance and order, every key number is correct (torque, pressure, "
        "capacity, RPM, time), and every page the answer cites is inside the "
        "allowed answer pages. A missing step or a wrong key number is partial. A "
        "plausible but wrong sequence scores low. Trust the reference over the "
        "agent."
    ),
    "out-of-scope": (
        "The premise has no answer in this manual. 1.0 only when the answer "
        "plainly says the manual does not contain the information and invents "
        "nothing: no value, no unit, no part number, and no page citation. Fluent "
        "invention — a wrong value or a fabricated page — is the worst outcome: "
        "score 0.0. Naming one close real fact to explain the absence is still a "
        "pass. Trust the reference over the agent."
    ),
}

JUDGE_SYSTEM = """You are a strict, fair evaluator of a grounded repair-manual \
assistant. The manual is the operator guide for an outboard motor. Apply ONLY the \
rubric given. Be skeptical of confident, fluent answers — fluency is not \
correctness. Treat the reference answer and the allowed answer pages as \
authoritative, and trust them over the agent. Penalize an uncited value, a wrong \
unit or qualifier, and any invented fact or page heavily.

Respond with EXACTLY ONE json object, no prose, no code fences:
  {"reason": "<1-3 sentences, written BEFORE you decide the score>",
   "score": <float 0.0-1.0>,
   "passed": <true|false>}
"""

_PAGE_RE = re.compile(r"\[\s*page\s+(\d+)\s*\]", re.IGNORECASE)


class Judgement(BaseModel):
    """The judge's verdict on one (case, answer) pair."""

    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    reason: str


def cited_pages(answer: str) -> list[int]:
    """Every distinct `[Page N]` number in the answer, in first-seen order."""
    seen: list[int] = []
    for match in _PAGE_RE.finditer(answer):
        page = int(match.group(1))
        if page not in seen:
            seen.append(page)
    return seen


def citation_precision(answer: str, expected_pages: Iterable[int]) -> float:
    """|cited ∩ expected| / |cited|.

    An answer that cites nothing scores 0.0: it grounds nothing, so it has no
    precision.
    """
    cited = set(cited_pages(answer))
    if not cited:
        return 0.0
    return len(cited & set(expected_pages)) / len(cited)


def rubric_for(category: str) -> str:
    """The rubric text for one category, or a ValueError for an unknown one."""
    rubric = RUBRICS.get(category)
    if rubric is None:
        raise ValueError(f"no rubric for category {category!r}")
    return rubric


def parse_judgement(raw: str) -> dict:
    """Parse the judge's JSON, tolerating code fences and stray prose."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"no JSON object in the judge output: {raw!r}") from None
        return json.loads(match.group(0))


def judge(
    case: EvalCase,
    answer: str,
    *,
    ground_truth: str | None = None,
    expected_pages: Iterable[int] | None = None,
) -> Judgement:
    """Score one markdown answer against its case. Returns a structured verdict.

    `ground_truth` overrides `case.expected`, and `expected_pages` overrides
    `case.answer_pages`, when a caller computes a reference of its own.
    """
    rubric = rubric_for(case.category)
    settings = get_settings()
    reference = ground_truth if ground_truth is not None else case.expected
    pages = tuple(case.answer_pages if expected_pages is None else expected_pages)
    pages_text = (
        ", ".join(str(page) for page in pages)
        if pages
        else "none — this question is out of scope"
    )

    user = f"""Rubric: {rubric}

Question:
{case.question}

Reference answer (authoritative):
{reference}

Allowed answer pages (authoritative): {pages_text}

Agent answer to evaluate:
{answer}
"""
    reply = llm.chat(
        [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": user},
        ],
        settings.eval_judge_model,
        params={
            "reasoning_effort": settings.eval_judge_reasoning_effort,
            "temperature": 0.0,
        },
    )
    obj = parse_judgement(reply.get("content") or "")
    if obj.get("score") is None:
        raise ValueError(f"the judge returned no score: {obj!r}")
    # Clamp, because a model can overshoot the 0.0-1.0 range.
    score = min(1.0, max(0.0, float(obj["score"])))
    return Judgement(
        score=score,
        passed=bool(obj.get("passed", score >= settings.eval_pass_threshold)),
        reason=str(obj.get("reason", "")),
    )


__all__ = [
    "JUDGE_SYSTEM",
    "RUBRICS",
    "Judgement",
    "citation_precision",
    "cited_pages",
    "judge",
    "parse_judgement",
    "rubric_for",
]
