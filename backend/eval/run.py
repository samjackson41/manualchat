"""Eval runner — run the 16 questions through the agent and score them.

Flow:
    for each case:
        run the agent once (ask) -> markdown answer
        judge the answer against the reference and the answer pages
        compute citation precision in code
    aggregate -> pass rate overall and per category
    print the table, the failures, and the fabricated count
    exit non-zero when a gate fails

The runner is the only module in this package that calls the agent and the LLM.
The dataset loader and the judge stay pure libraries.

Run it from the repository root, against an ingested eval manual:

    cd manualchat
    EVAL_VEHICLE_ID=<vehicle_id> uv run --project backend python -m backend.eval.run

`EVAL_VEHICLE_ID` names the vehicle that owns the eval manual, and it comes from
the configuration (DECISIONS P1). The run needs `OPENROUTER_API_KEY` and an
indexed manual, so it stays out of the default cheap CI (DECISIONS T3).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass

from backend.agent.graph import ask
from backend.config import get_settings
from backend.eval.dataset import OUT_OF_SCOPE, EvalCase, load_cases
from backend.eval.judge import Judgement, citation_precision, cited_pages, judge


@dataclass
class Result:
    """One case, its answer, and how it scored."""

    case: EvalCase
    answer: str
    judgement: Judgement
    precision: float
    fabricated: bool

    @property
    def passed(self) -> bool:
        """A case passes when the judge passes it and it invented nothing."""
        return self.judgement.passed and not self.fabricated


@dataclass
class Summary:
    """The aggregate the report prints and the gates read."""

    overall_pass_rate: float
    per_category: dict[str, tuple[int, int]]  # category -> (passed, total)
    citation_precision: float
    fabricated: int


def is_fabrication(case: EvalCase, answer: str, judgement: Judgement) -> bool:
    """True when an out-of-scope answer invents a value or a page.

    The manual holds no answer to an out-of-scope question, so a cited page is
    an invented page. A judge score of 0.0 says the same thing in words. Either
    signal fails the case, whatever the score.
    """
    if case.category != OUT_OF_SCOPE:
        return False
    return bool(cited_pages(answer)) or judgement.score <= 0.0


def run_case(
    case: EvalCase, *, model: str | None = None, vehicle_id: str | None = None
) -> Result:
    """Run one case end to end: agent, then judge, then the precision count."""
    answer = ask(case.question, model=model, vehicle_id=vehicle_id)
    verdict = judge(case, answer)
    return Result(
        case=case,
        answer=answer,
        judgement=verdict,
        precision=citation_precision(answer, case.answer_pages),
        fabricated=is_fabrication(case, answer, verdict),
    )


def run_all(
    cases: list[EvalCase] | None = None,
    *,
    model: str | None = None,
    vehicle_id: str | None = None,
) -> list[Result]:
    """Run every case. Returns one Result per case, in set order."""
    cases = load_cases() if cases is None else cases
    return [run_case(case, model=model, vehicle_id=vehicle_id) for case in cases]


def _summarize(results: list[Result]) -> Summary:
    """Fold the results into the pass rates, precision, and fabricated count."""
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    per_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for result in results:
        bucket = per_category[result.case.category]
        bucket[1] += 1
        bucket[0] += int(result.passed)
    in_scope = [r for r in results if r.case.category != OUT_OF_SCOPE]
    precision = (
        sum(result.precision for result in in_scope) / len(in_scope) if in_scope else 0.0
    )
    return Summary(
        overall_pass_rate=(passed / total if total else 0.0),
        per_category={name: (bucket[0], bucket[1]) for name, bucket in per_category.items()},
        citation_precision=precision,
        fabricated=sum(1 for result in results if result.fabricated),
    )


def report(results: list[Result]) -> Summary:
    """Print the pass table and every failure's reason. Returns the Summary."""
    if not results:
        print("No results.")
        return Summary(0.0, {}, 0.0, 0)

    summary = _summarize(results)
    total = len(results)
    passed = sum(1 for result in results if result.passed)

    print(f"\nOverall: {passed}/{total} passed ({summary.overall_pass_rate:.0%})")
    print("\nBy category:")
    for category in sorted(summary.per_category):
        cat_pass, cat_total = summary.per_category[category]
        print(f"  {category:<13} {cat_pass}/{cat_total} ({cat_pass / cat_total:.0%})")
    print(f"\nCitation precision (in-scope): {summary.citation_precision:.2f}")
    print(f"Fabricated out-of-scope answers: {summary.fabricated}")

    failures = [result for result in results if not result.passed]
    if not failures:
        print("\nNo failures. Read the reasons anyway — a clean run can hide weak rubrics.")
        return summary

    print("\nFailures:")
    for result in failures:
        flag = "  FABRICATED" if result.fabricated else ""
        print(
            f"  [{result.case.id}] score={result.judgement.score:.2f} "
            f"precision={result.precision:.2f}{flag}"
        )
        print(f"      reason: {result.judgement.reason}")
    return summary


def main() -> int:
    """Run the set, print the report, and apply the gates."""
    settings = get_settings()
    vehicle_id = settings.eval_vehicle_id.strip()
    if not vehicle_id:
        print(
            "EVAL_VEHICLE_ID is not set. Export the vehicle id that owns the "
            "eval manual, e.g. EVAL_VEHICLE_ID=<id>.",
            file=sys.stderr,
        )
        return 2

    print(
        f"Eval: {len(load_cases())} cases | vehicle {vehicle_id} | "
        f"model {settings.model_default} | judge {settings.eval_judge_model}"
    )
    summary = report(run_all(vehicle_id=vehicle_id))

    gates = {
        f"pass rate >= {settings.eval_min_pass_rate:.0%}": (
            summary.overall_pass_rate >= settings.eval_min_pass_rate
        ),
        f"citation precision >= {settings.eval_citation_precision_min:.2f}": (
            summary.citation_precision >= settings.eval_citation_precision_min
        ),
        "no fabricated out-of-scope answer": summary.fabricated == 0,
    }
    print("\nGates:")
    for name, ok in gates.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(gates.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
