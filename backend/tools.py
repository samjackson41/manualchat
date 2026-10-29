"""Agent tools — ManualChat's tool-calling extension seam.

Each tool is an OpenAI function-calling schema plus a small Python executor.
The graph binds the schemas to the model call (backend.llm.chat) and
TOOL_REGISTRY runs whichever tool the model picks. RAG tools (search_manual,
extract_specs, get_page_text) land here for IMPLEMENTATION Task 4.
"""

import ast
import json
import operator
import re
from typing import Callable

from backend import retrieval, storage
from backend.config import get_settings
from backend.schemas import (
    ExtractSpecsResult,
    GetPageTextResult,
    IngestTable,
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


# --- RAG tools (IMPLEMENTATION Task 4) ------------------------------------
# The agent's retrieval surface. Each executor calls the real retrieval
# backend (backend.retrieval) or reads a manual's ingest output from disk, then
# serializes the matching output contract from backend.schemas to JSON.

# Words that never identify a spec row on their own; they are dropped before
# matching a subject against table captions and row labels.
_STOPWORDS = {
    "the", "a", "an", "of", "for", "and", "to", "in", "on", "with", "at",
    "by", "or", "is", "are", "be", "as", "it", "this", "that", "from",
}


def _tokens(text: str) -> set[str]:
    """Lowercase alphanumeric words, minus stopwords, for loose subject matching."""
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS}


def _read_tables(manual_id: str) -> list[IngestTable]:
    """Read one manual's extracted tables, or an empty list when absent."""
    path = storage.manual_dir(manual_id) / "tables.json"
    if not path.is_file():
        return []
    return [IngestTable.model_validate(t) for t in json.loads(path.read_text())]


def _enabled_manual_ids(vehicle_id: str, manual_id: str | None) -> list[str]:
    """Source manual ids for a spec lookup, skipping disabled manuals (DECISIONS M1).

    Mirrors ``retrieval.search``: a manual named from another vehicle matches
    nothing, and a disabled manual never surfaces its specs.
    """
    if manual_id:
        manual = storage.get_manual(manual_id)
        if manual is None or manual.vehicle_id != vehicle_id or not manual.enabled:
            return []
        return [manual_id]
    return [
        m.manual_id
        for m in storage.list_manuals()
        if m.vehicle_id == vehicle_id and m.enabled
    ]


def _parse_pipe_table(markdown: str) -> list[tuple[str, str]]:
    """Return (item, value) pairs from a Markdown pipe table's data rows.

    A pipe table is a header row, a ``|---|`` separator row, then data rows.
    Each data row's first cell is the item (row label); the remaining cells are
    joined into the value. Rows with an empty item or value are skipped.
    """
    lines = [ln.strip() for ln in markdown.splitlines() if ln.strip().startswith("|")]
    rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines]
    data: list[list[str]] = []
    for row in rows:
        if all(set(c) <= set("-: ") for c in row if c):
            continue  # the separator row
        data.append(row)
    if data:
        data = data[1:]  # drop the header row
    pairs: list[tuple[str, str]] = []
    for row in data:
        if not row or not row[0]:
            continue
        value = " | ".join(c for c in row[1:] if c)
        if not value:
            continue
        pairs.append((row[0], value))
    return pairs


def search_manual(
    query: str,
    vehicle_id: str,
    manual_id: str | None = None,
    top_k: int | None = None,
) -> str:
    """Search the manual and return reranked chunks with page citations."""
    top_n = top_k if top_k is not None else get_settings().retrieval_top_n
    chunks = retrieval.search(query, vehicle_id, manual_id, top_n=top_n)
    return SearchResult(query=query, results=chunks).model_dump_json()


def extract_specs(
    subject: str,
    vehicle_id: str,
    manual_id: str | None = None,
) -> str:
    """Return exact key/value rows from the manual's tables that match a subject.

    The subject is matched loosely against each table's caption and row labels;
    matched rows are returned verbatim (never guessed). An empty ``specs`` list
    means no table matched.
    """
    manual_ids = _enabled_manual_ids(vehicle_id, manual_id)
    subject_tokens = _tokens(subject)
    specs: list[SpecItem] = []
    for mid in manual_ids:
        for table in _read_tables(mid):
            caption_tokens = _tokens(table.caption or "")
            for item, value in _parse_pipe_table(table.markdown):
                if subject_tokens & (_tokens(item) | caption_tokens):
                    specs.append(
                        SpecItem(
                            item=item,
                            value=value,
                            unit="",
                            page_number=table.page_number,
                            manual_id=mid,
                        )
                    )
    return ExtractSpecsResult(subject=subject, specs=specs).model_dump_json()


def get_page_text(
    page_numbers: list[int],
    manual_id: str,
    vehicle_id: str | None = None,
) -> str:
    """Return the full, unchunked text of each requested physical page.

    Page numbers are physical (1-indexed), matching the ``page_NNNN.txt``
    filenames (DECISIONS D12). Pages with no file on disk are skipped.
    """
    pages: list[PageText] = []
    for page_number in page_numbers:
        path = storage.manual_dir(manual_id) / "page_text" / f"page_{page_number:04d}.txt"
        if path.is_file():
            pages.append(PageText(page_number=page_number, text=path.read_text()))
    return GetPageTextResult(manual_id=manual_id, pages=pages).model_dump_json()


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
                    "manual_id": {
                        "type": "string",
                        "description": "Optional manual identifier to narrow the search.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Optional number of chunks to return (default 5).",
                    },
                },
                "required": ["query"],
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
                    "manual_id": {
                        "type": "string",
                        "description": "Optional manual identifier to narrow the lookup.",
                    },
                },
                "required": ["subject"],
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