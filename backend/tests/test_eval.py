"""Unit tests for the eval harness's pure parts.

These run without a live LLM or an API key: rubric selection, the tolerant
judge-output parser, citation-precision math, the fabrication rule, and the
dataset loader (DECISIONS T1/T3).
"""

import json

import pytest

from backend.eval.dataset import CATEGORIES, EvalCase, load_cases
from backend.eval.judge import (
    RUBRICS,
    Judgement,
    citation_precision,
    cited_pages,
    judge,
    parse_judgement,
    rubric_for,
)
from backend.eval.run import is_fabrication


def test_every_category_has_a_rubric():
    for category in CATEGORIES:
        assert rubric_for(category) in RUBRICS.values()


def test_unknown_category_has_no_rubric():
    with pytest.raises(ValueError):
        rubric_for("nonsense")


def test_judge_rejects_an_unknown_category_before_the_llm_call():
    case = EvalCase("x", "q", "nonsense", (), "e")
    with pytest.raises(ValueError):
        judge(case, "an answer")


def test_parse_judgement_reads_plain_json():
    obj = parse_judgement('{"reason": "ok", "score": 1.0, "passed": true}')
    assert obj == {"reason": "ok", "score": 1.0, "passed": True}


def test_parse_judgement_tolerates_a_code_fence():
    raw = '```json\n{"reason": "ok", "score": 0.5, "passed": false}\n```'
    assert parse_judgement(raw)["score"] == 0.5


def test_parse_judgement_tolerates_stray_prose():
    raw = 'Here is my verdict: {"reason": "no page", "score": 0.0} — done.'
    assert parse_judgement(raw)["reason"] == "no page"


def test_parse_judgement_raises_without_a_json_object():
    with pytest.raises(ValueError):
        parse_judgement("no json here")


def test_cited_pages_are_distinct_and_ordered():
    answer = "Torque is 20 [Page 15], see also [page 14] and again [Page 15]."
    assert cited_pages(answer) == [15, 14]


def test_citation_precision_counts_only_allowed_pages():
    answer = "A [Page 14] and B [Page 15] and C [Page 99]"
    assert citation_precision(answer, [14, 15]) == pytest.approx(2 / 3)


def test_citation_precision_is_one_when_every_page_is_allowed():
    assert citation_precision("see [Page 14]", [14, 15]) == 1.0


def test_citation_precision_is_zero_when_uncited():
    assert citation_precision("no citations at all", [14, 15]) == 0.0


def test_fabrication_flags_a_cited_out_of_scope_answer():
    """A page citation on an out-of-scope case is an invented page."""
    case = EvalCase("o", "q", "out-of-scope", (), "not found")
    verdict = Judgement(score=0.9, passed=True, reason="looks fine")
    assert is_fabrication(case, "The manual says 0.030 in. [Page 12].", verdict)


def test_fabrication_flags_a_zero_score_on_out_of_scope():
    """A fluent invention scores 0.0; the score alone fails the case."""
    case = EvalCase("o", "q", "out-of-scope", (), "not found")
    verdict = Judgement(score=0.0, passed=False, reason="invented a value")
    assert is_fabrication(case, "The manual does not contain it.", verdict)


def test_a_clean_refusal_is_not_a_fabrication():
    case = EvalCase("o", "q", "out-of-scope", (), "not found")
    verdict = Judgement(score=1.0, passed=True, reason="declined")
    assert not is_fabrication(case, "The manual does not contain information on this.", verdict)


def test_a_wrong_in_scope_answer_is_not_a_fabrication():
    case = EvalCase("s", "q", "spec", (14,), "e")
    verdict = Judgement(score=0.0, passed=False, reason="wrong")
    assert not is_fabrication(case, "It is 99. [Page 14]", verdict)


def test_load_cases_reads_the_16_case_set():
    cases = load_cases()
    assert len(cases) == 16
    assert len({case.id for case in cases}) == 16
    counts = {category: sum(c.category == category for c in cases) for category in CATEGORIES}
    assert counts == {"spec": 6, "procedure": 5, "out-of-scope": 5}


def test_load_cases_derives_an_id_when_one_is_missing(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "question": "q1",
                    "category": "spec",
                    "answer_pages": [3],
                    "expected": "e1",
                }
            ]
        )
    )
    (case,) = load_cases(path)
    assert case.id == "spec-01"
    assert case.answer_pages == (3,)


def test_load_cases_rejects_an_unknown_category(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps([{"question": "q", "category": "other", "expected": "e"}])
    )
    with pytest.raises(ValueError):
        load_cases(path)
