"""Feature tests for the calculator tool.

The calculator is ManualChat's only tool today. These pin down both its
arithmetic and its safety boundary: it walks a whitelisted AST, so anything
else must be rejected rather than executed.
"""

import pytest

from backend.tools import calculator


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("3*7+2", "23"),
        ("2**10", "1024"),
        ("7//2", "3"),
        ("7/2", "3.5"),
        ("(1+2)*3", "9"),
        ("2.5+2.5", "5"),
        ("10%3", "1"),
        ("-5", "-5"),
    ],
)
def test_calculator_evaluates(expression, expected):
    assert calculator(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('ls')",
        "open('file')",
        "print('hi')",
        "1/0",
        "x + 1",
        "1 or 2",
    ],
)
def test_calculator_rejects_unsafe_or_invalid(expression):
    assert calculator(expression).startswith("Error:")
