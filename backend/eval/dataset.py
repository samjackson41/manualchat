"""The eval set loader — a pure library.

`backend/tests/eval_questions.json` holds the 16 fixed questions for the
accuracy run. Each case names the question, its category, the manual pages that
answer it, and the gold answer. The wiki page `Accuracy-Eval-Set` is the human
copy of the same table.

Categories:
    spec         — an exact value from a table: a torque, a capacity, a part
                   number.
    procedure    — a step-by-step how-to.
    out-of-scope — the manual holds no answer, so the agent must say so and
                   invent nothing.

Importing this module has no side effects. It reads the JSON file only when
`load_cases()` runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# `backend/eval/dataset.py` -> `backend/tests/eval_questions.json`.
DEFAULT_CASES_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "eval_questions.json"
)

SPEC = "spec"
PROCEDURE = "procedure"
OUT_OF_SCOPE = "out-of-scope"
CATEGORIES = (SPEC, PROCEDURE, OUT_OF_SCOPE)


@dataclass(frozen=True)
class EvalCase:
    """One question plus the reference that a passing answer must match.

    `answer_pages` lists the physical PDF pages the manual answers on. An
    out-of-scope case lists no page.
    """

    id: str
    question: str
    category: str
    answer_pages: tuple[int, ...]
    expected: str


def load_cases(path: Path | str = DEFAULT_CASES_PATH) -> list[EvalCase]:
    """Read the eval set into `EvalCase` values.

    A case without an `id` gets `{category}-{index}` (1-based), so every case
    keeps a stable name in the report. An unknown category is an error, because
    it has no rubric.
    """
    raw = json.loads(Path(path).read_text())
    cases: list[EvalCase] = []
    for index, item in enumerate(raw, start=1):
        category = item["category"]
        if category not in CATEGORIES:
            raise ValueError(f"unknown category {category!r} in the eval set")
        cases.append(
            EvalCase(
                id=item.get("id") or f"{category}-{index:02d}",
                question=item["question"],
                category=category,
                answer_pages=tuple(int(page) for page in item.get("answer_pages") or ()),
                expected=item["expected"],
            )
        )
    return cases


__all__ = [
    "CATEGORIES",
    "DEFAULT_CASES_PATH",
    "EvalCase",
    "OUT_OF_SCOPE",
    "PROCEDURE",
    "SPEC",
    "load_cases",
]
