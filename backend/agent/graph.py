"""LangGraph agent — a supervisor, worker, and synthesize topology.

The supervisor reads the question and what the worker has found, and decides
whether the worker keeps searching the manual or the graph moves to synthesis.
The worker runs the tool loop (calculator plus the three RAG tools). The
synthesize node writes the final markdown answer with `[Page N]` citations.

The model the user picked (`state["model"]`, DECISIONS M1/M3) selects a tier.
A tier fixes the supervisor and worker models and their reasoning effort:

    fast -> supervisor Flash @ high, worker Flash @ low
    pro  -> supervisor Pro   @ max,  worker Flash @ high

The shape mirrors the cohort supervisor/specialist graph, adapted to one
retrieval worker:

    supervisor --(route)--> worker --> supervisor --> ... --> synthesize

One node does one job, and every model call goes through `backend.llm`.
"""

import inspect
import json
import operator
from typing import Annotated, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from backend import llm
from backend.config import SuperSubTier, get_settings
from backend.tools import TOOL_REGISTRY, TOOL_SCHEMAS


class AgentState(TypedDict):
    """Graph state.

    `messages` is the conversation (an Annotated list so LangGraph merges node
    outputs with `add_messages`). `model` is a per-request override of the
    config default — DECISIONS M3 (session-scoped runtime override); it selects
    the tier. `gathered` holds one findings block per worker hop, so the
    supervisor sees what the worker has found. `next` is the supervisor's
    routing decision, and `hops` counts worker runs (the hop cap guard).
    `vehicle_id` scopes the conversation to one vehicle (SPECIFICATION §6).
    """

    messages: Annotated[list[BaseMessage], add_messages]
    model: str
    vehicle_id: str | None
    stream: bool
    gathered: Annotated[list[str], operator.add]
    next: str
    hops: int


_ROLE_MAP = {
    "human": "user",
    "ai": "assistant",
    "system": "system",
    "tool": "tool",
}


def _serialize(messages: list[BaseMessage]) -> list[dict]:
    """Convert langchain messages back to OpenAI chat format for llm.chat."""
    out: list[dict] = []
    for message in messages:
        mtype = getattr(message, "type", "human")
        item = {"role": _ROLE_MAP.get(mtype, "user")}
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        item["content"] = content
        if mtype == "tool":
            item["tool_call_id"] = getattr(message, "tool_call_id", None)
        if mtype == "ai" and getattr(message, "tool_calls", None):
            item["tool_calls"] = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["args"]),
                    },
                }
                for call in message.tool_calls
            ]
        out.append(item)
    return out


def _with_system_prompt(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Lead the messages with the grounding prompt; kept out of state."""
    system = SystemMessage(content=get_settings().agent_system_prompt)
    return [system, *messages]


def _tool_calls_from_reply(reply: dict) -> list[dict]:
    """Convert an OpenRouter assistant reply's tool_calls to langchain shape."""
    tool_calls = []
    for call in reply.get("tool_calls") or []:
        try:
            args = json.loads(call["function"]["arguments"] or "{}")
        except (json.JSONDecodeError, TypeError):
            args = {}
        tool_calls.append(
            {"id": call["id"], "name": call["function"]["name"], "args": args}
        )
    return tool_calls


def _question(state: AgentState) -> str:
    """The user's question — the first human message."""
    for message in state["messages"]:
        if getattr(message, "type", None) != "human":
            continue
        content = message.content
        if isinstance(content, list):
            return "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        return content
    return ""


def _execute_tool_calls(
    tool_calls: list[dict], vehicle_id: str | None
) -> list[ToolMessage]:
    """Run pending tool calls, scoping them to the conversation's vehicle.

    The model cannot know the vehicle id, so the state's value is merged into
    every tool argument and overrides any value the model supplied. Tools that
    do not take a ``vehicle_id`` parameter (calculator) are left alone.
    """
    tool_messages: list[ToolMessage] = []
    for call in tool_calls:
        fn = TOOL_REGISTRY.get(call["name"])
        if fn is None:
            output = f"Error: unknown tool '{call['name']}'"
        else:
            try:
                args = dict(call["args"])
                if "vehicle_id" in inspect.signature(fn).parameters:
                    args["vehicle_id"] = vehicle_id
                output = fn(**args)
            except TypeError as exc:
                output = f"Error: bad arguments for '{call['name']}': {exc}"
        tool_messages.append(
            ToolMessage(content=output, name=call["name"], tool_call_id=call["id"])
        )
    return tool_messages


# The supervisor plans and writes the final answer; this prompt is its routing
# instruction. The worker and synthesize nodes keep the grounding system prompt.
_SUPERVISOR_SYSTEM = (
    "You are the supervisor of a grounded repair-manual assistant. Read the "
    "question and the worker's findings, then decide the next step. Reply with "
    "one word: 'worker' to keep searching the manual, or 'synthesize' when the "
    "findings are enough to write the final answer."
)


def supervisor_node(state: AgentState) -> dict:
    """Decide whether the worker keeps searching, or the graph synthesizes."""
    settings = get_settings()
    tier = settings.tier_for_model(state["model"])
    gathered = state.get("gathered") or []
    hops = state.get("hops", 0)

    # Gather at least once, and force synthesis at the hop cap so a confused
    # supervisor cannot loop forever.
    if not gathered:
        return {"next": "worker", "hops": hops}
    if hops >= settings.agent_max_hops:
        return {"next": "synthesize", "hops": hops}

    reply = llm.chat(
        [
            {"role": "system", "content": _SUPERVISOR_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Question: {_question(state)}\n\n"
                    f"Findings so far:\n" + "\n\n".join(gathered) + "\n\n"
                    "Reply with one word: worker or synthesize."
                ),
            },
        ],
        tier.supervisor_model,
        params={"reasoning_effort": tier.supervisor_effort},
    )
    choice = (reply.get("content") or "").strip().lower()
    return {"next": "worker" if choice.startswith("worker") else "synthesize", "hops": hops}


def worker_node(state: AgentState) -> dict:
    """Run the retrieval tool loop and record what the worker found.

    Offers the tool schemas to the tier's sub model and runs the calculator and
    the three RAG tools, injecting the state's ``vehicle_id``. The findings are
    the model's last text turn, once it stops asking for tools.
    """
    settings = get_settings()
    tier = settings.tier_for_model(state["model"])
    gathered = state.get("gathered") or []

    user = _question(state)
    if gathered:
        user = "Findings so far:\n" + "\n\n".join(gathered) + "\n\nQuestion: " + user
    messages = _with_system_prompt([HumanMessage(content=user)])

    findings = ""
    for _ in range(settings.agent_max_tool_steps):
        reply = llm.chat(
            _serialize(messages),
            tier.sub_model,
            params={"reasoning_effort": tier.sub_effort},
            tools=TOOL_SCHEMAS,
        )
        message = AIMessage(
            content=reply.get("content") or "",
            tool_calls=_tool_calls_from_reply(reply),
        )
        messages.append(message)
        findings = message.content or findings
        if not message.tool_calls:
            break
        messages.extend(
            _execute_tool_calls(message.tool_calls, state.get("vehicle_id"))
        )

    return {"gathered": [findings], "hops": state.get("hops", 0) + 1}


def synthesize_node(state: AgentState) -> dict:
    """Write the final markdown answer with `[Page N]` citations."""
    tier = get_settings().tier_for_model(state["model"])
    findings = "\n\n".join(state.get("gathered") or []) or "(the worker found nothing)"
    messages = _with_system_prompt(
        [
            HumanMessage(
                content=(
                    f"Question: {_question(state)}\n\n"
                    f"Findings from the manual:\n{findings}\n\n"
                    "Write the final answer."
                )
            )
        ]
    )

    if state.get("stream"):
        answer = _stream_answer(messages, tier)
    else:
        reply = llm.chat(
            _serialize(messages),
            tier.supervisor_model,
            params={"reasoning_effort": tier.supervisor_effort},
        )
        answer = reply.get("content") or ""
    return {"messages": [AIMessage(content=answer)]}


def _stream_answer(messages: list[BaseMessage], tier: SuperSubTier) -> str:
    """Stream the final answer to the client, returning the assembled text.

    Each content delta goes through the custom stream writer, consumed by
    ``POST /chat/stream`` via ``stream_mode="custom"``. Supervisor and worker
    reasoning is internal and is not streamed.
    """
    writer = get_stream_writer()
    parts: list[str] = []
    for delta in llm.stream_chat(
        _serialize(messages),
        tier.supervisor_model,
        params={"reasoning_effort": tier.supervisor_effort},
    ):
        if delta.get("content"):
            parts.append(delta["content"])
            writer({"type": "token", "content": delta["content"]})
    return "".join(parts)


def _route_supervisor(state: AgentState) -> str:
    """After `supervisor`, go to `worker` or `synthesize`."""
    return "worker" if state.get("next") == "worker" else "synthesize"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("worker", worker_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_supervisor,
        {"worker": "worker", "synthesize": "synthesize"},
    )
    graph.add_edge("worker", "supervisor")
    graph.add_edge("synthesize", END)
    return graph.compile()


# Compiled at import so the API layer shares one instance.
graph = build_graph()