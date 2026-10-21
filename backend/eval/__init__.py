"""Evaluation harness — an LLM-as-judge run over the 16-question accuracy set.

Modules:
    dataset.py — the fixed question set loader (pure, no LLM, no network).
    judge.py   — rubric scoring of one markdown answer; calls the LLM only when
                 the runner invokes it.
    run.py     — the runner; start it with `python -m backend.eval.run`.

Importing this package has no side effects. The package re-exports nothing, so
`backend.eval.judge` always names the module and never a function.
"""

