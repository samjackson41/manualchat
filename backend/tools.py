"""Agent tools — ManualChat's tool-calling extension seam.

Each tool is an OpenAI function-calling schema plus a small Python executor.
The graph binds the schemas to the model call (backend.llm.chat) and
TOOL_REGISTRY runs whichever tool the model picks. RAG tools (search_manual,
extract_specs, get_page_text) land here for IMPLEMENTATION Task 4.
"""

import ast
import operator
from typing import Callable

_BINOPS: dict[type, Callable] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARYOPS: dict[type, Callable] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval(node: ast.AST):
    """Walk a whitelisted AST; anything else raises instead of executing."""
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        return _UNARYOPS[type(node.op)](_eval(node.operand))
    raise ValueError("only + - * / // % ** and parentheses are allowed")


def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression without Python eval()."""
    try:
        result = _eval(ast.parse(expression, mode="eval"))
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        return f"Error: cannot compute '{expression}': {exc}"
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return str(result)


# OpenAI function-calling schemas (bound to the model in llm.chat).
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": (
                "Evaluate a simple arithmetic expression and return the numeric "
                "result. Supports + - * / // % ** and parentheses, with integer "
                "or decimal numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Arithmetic expression, e.g. '3*7+2'.",
                    },
                },
                "required": ["expression"],
            },
        },
    },
]

# Tool name -> executor. The graph looks results up here after the model picks a tool.
TOOL_REGISTRY: dict[str, Callable] = {"calculator": calculator}