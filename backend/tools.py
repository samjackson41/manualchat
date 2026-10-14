"""Agent tools — ManualChat's tool-calling extension seam.

Each tool is an OpenAI function-calling schema plus a small Python executor.
The graph binds the schemas to the model call (backend.llm.chat) and
TOOL_REGISTRY runs whichever tool the model picks. RAG tools (search_manual,
extract_specs, get_page_text) land here for IMPLEMENTATION Task 4.
"""

import ast
import operator
from typing import Callable

from backend.schemas import (
    ChunkPayload,
    ExtractSpecsResult,
    GetPageTextResult,
    PageText,
    SearchResult,
    SpecItem,
)

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


# --- RAG tools (STUBS) -----------------------------------------------------
# IMPLEMENTATION Task 4. These are the agent's retrieval surface. The bodies
# are STUBS: they return sample fixtures so the chat -> tools -> chat loop can
# be proven end to end before real Qdrant retrieval lands. Task 4 swaps the
# bodies, not the contracts.
#
# The fixtures hold no manual-specific identity. Every stub answers for any
# vehicle and echoes back the ids it is given, as real retrieval will.

# Placeholder ids for the fixture payloads; each call overwrites them.
_STUB_VEHICLE_ID = "demo_vehicle"
_STUB_MANUAL_ID = "demo_manual"

_STUB_CHUNKS: list[ChunkPayload] = [
    ChunkPayload(
        text=(
            "Engine oil and oil filter change: 1. Remove the oil drain bolt at "
            "the bottom of the crankcase and drain the oil. 2. Remove the oil "
            "filter. 3. Install a new filter and the drain bolt, then refill "
            "with the specified amount of engine oil."
        ),
        vehicle_id=_STUB_VEHICLE_ID,
        manual_id=_STUB_MANUAL_ID,
        page_number=82,
        section_name="Engine oil and oil filter",
        score=0.93,
    ),
    ChunkPayload(
        text="Tightening torque — engine oil drain bolt (M14): 30 N·m (22 ft·lb).",
        vehicle_id=_STUB_VEHICLE_ID,
        manual_id=_STUB_MANUAL_ID,
        page_number=24,
        section_name="Specifications",
        is_table=True,
        score=0.87,
    ),
]

_STUB_SPECS: list[SpecItem] = [
    SpecItem(item="Engine oil drain bolt", value="30", unit="N·m (22 ft·lb)", page_number=24),
    SpecItem(item="Engine oil capacity (oil change)", value="2.0", unit="L", page_number=24),
    SpecItem(item="Engine oil capacity (overhaul)", value="2.1", unit="L", page_number=24),
    SpecItem(item="Final gear oil capacity", value="3.0", unit="L", page_number=24),
]

_STUB_PAGES: list[PageText] = [
    PageText(
        page_number=82,
        text=(
            "[82] ENGINE OIL AND OIL FILTER — Remove the oil drain bolt and "
            "drain the engine oil into a suitable container. Install a new "
            "sealing washer, refit the bolt, and hand-tighten."
        ),
    ),
    PageText(
        page_number=83,
        text=(
            "[83] — Refill with the specified engine oil (2.0 L for an oil "
            "change) and tighten the drain bolt to 30 N·m (22 ft·lb)."
        ),
    ),
]


def search_manual(
    query: str,
    vehicle_id: str,
    manual_id: str | None = None,
    top_k: int | None = None,  # accepted for the contract; unused until real retrieval
) -> str:
    """STUB — return sample chunks for the requested vehicle; real Qdrant search lands in Task 4."""
    chunks = [
        chunk.model_copy(
            update={
                "vehicle_id": vehicle_id,
                "manual_id": manual_id or chunk.manual_id,
            }
        )
        for chunk in _STUB_CHUNKS
    ]
    return SearchResult(query=query, results=chunks).model_dump_json()


def extract_specs(
    subject: str,
    vehicle_id: str,
    manual_id: str | None = None,
) -> str:
    """STUB — return sample specs for any vehicle; real table retrieval lands in Task 4."""
    return ExtractSpecsResult(subject=subject, specs=_STUB_SPECS).model_dump_json()


def get_page_text(
    page_numbers: list[int],
    manual_id: str,
    vehicle_id: str | None = None,
) -> str:
    """STUB — return sample page text for any manual; real unchunked retrieval lands in Task 4."""
    return GetPageTextResult(manual_id=manual_id, pages=_STUB_PAGES).model_dump_json()


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
    {
        "type": "function",
        "function": {
            "name": "search_manual",
            "description": (
                "Search the repair manual for chunks relevant to a natural-language "
                "query, scoped to a vehicle. Returns ranked text chunks with page "
                "numbers. Use for procedural steps and general how-to questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query, e.g. 'how to change the engine oil'.",
                    },
                    "vehicle_id": {
                        "type": "string",
                        "description": "Vehicle identifier, e.g. 'demo_vehicle'.",
                    },
                    "manual_id": {
                        "type": "string",
                        "description": "Optional manual identifier to narrow the search.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Optional number of chunks to return (default 5).",
                    },
                },
                "required": ["query", "vehicle_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_specs",
            "description": (
                "Extract exact key/value specifications (torques, fluid capacities, "
                "part numbers) from the manual's tables for a given subject. Returns "
                "verbatim values with units and page numbers — never paraphrased."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "The spec to look up, e.g. 'engine oil drain bolt torque'.",
                    },
                    "vehicle_id": {
                        "type": "string",
                        "description": "Vehicle identifier, e.g. 'demo_vehicle'.",
                    },
                    "manual_id": {
                        "type": "string",
                        "description": "Optional manual identifier to narrow the lookup.",
                    },
                },
                "required": ["subject", "vehicle_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_text",
            "description": (
                "Return the complete, unchunked text of one or more pages, for when "
                "a procedure spans consecutive paragraphs. Returns full page text "
                "with page numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page_numbers": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Printed page numbers to fetch, e.g. [82, 83].",
                    },
                    "manual_id": {
                        "type": "string",
                        "description": "Manual identifier to fetch pages from.",
                    },
                    "vehicle_id": {
                        "type": "string",
                        "description": "Optional vehicle identifier (contextual).",
                    },
                },
                "required": ["page_numbers", "manual_id"],
            },
        },
    },
]

# Tool name -> executor. The graph looks results up here after the model picks a tool.
TOOL_REGISTRY: dict[str, Callable] = {
    "calculator": calculator,
    "search_manual": search_manual,
    "extract_specs": extract_specs,
    "get_page_text": get_page_text,
}