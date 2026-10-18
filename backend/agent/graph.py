"""LangGraph agent — the iteration point for ManualChat.

A `chat -> tools -> chat` loop: the model may ask to run a tool, the `tools`
node executes it and feeds the result back as ToolMessages, and the loop repeats
until the model answers without a tool call. AgentState is unchanged from the
skeleton, so later work (RAG tools, memory) slots in without rework.

WHERE THE NEXT CHANGES GO (documented so the structure is obviously extensible):

  1. RAG             -> add `search_manual` / `extract_specs` / `get_page_text`
     tools per IMPLEMENTATION Task 4. They land in the SAME TOOL_SCHEMAS /
     TOOL_REGISTRY (backend.tools) — no graph change.

  2. Memory          -> add a `summary` field + compaction node (MEMORY_DESIGN
     §4-5) and a checkpointer (InMemorySaver, later RedisSaver).
"""

import inspect
import json
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from backend import llm
from backend.config import get_settings
from backend.tools import TOOL_REGISTRY, TOOL_SCHEMAS


class AgentState(TypedDict):
    """Graph state.

    `messages` is the conversation (an Annotated list so LangGraph merges
    node outputs with `add_messages`). `model` is a per-request override of the
    config default — DECISIONS M3 (session-scoped runtime override).
    `vehicle_id` scopes the conversation to one vehicle (SPECIFICATION §6);
    retrieval reads it once real Qdrant search lands (Task 4).
    """

    messages: Annotated[list[BaseMessage], add_messages]
    model: str
    vehicle_id: str | None


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


def chat_node(state: AgentState) -> dict:
    """Call OpenRouter (with tool schemas) and append the assistant's reply."""
    reply = llm.chat(
        _serialize(_with_system_prompt(state["messages"])),
        state["model"],
        tools=TOOL_SCHEMAS,
    )
    tool_calls = []
    for call in reply.get("tool_calls") or []:
        try:
            args = json.loads(call["function"]["arguments"] or "{}")
        except (json.JSONDecodeError, TypeError):
            args = {}
        tool_calls.append(
            {"id": call["id"], "name": call["function"]["name"], "args": args}
        )
    return {
        "messages": [
            AIMessage(content=reply.get("content") or "", tool_calls=tool_calls)
        ]
    }


def tool_node(state: AgentState) -> dict:
    """Run the pending tool calls, scoping them to the state's vehicle.

    The model cannot know the vehicle id, so the state's value is merged into
    every tool argument and overrides any value the model supplied. Tools that
    do not take a ``vehicle_id`` parameter (calculator) are left alone.
    """
    last = state["messages"][-1]
    tool_messages: list[ToolMessage] = []
    for call in last.tool_calls:
        fn = TOOL_REGISTRY.get(call["name"])
        if fn is None:
            output = f"Error: unknown tool '{call['name']}'"
        else:
            try:
                args = dict(call["args"])
                if "vehicle_id" in inspect.signature(fn).parameters:
                    args["vehicle_id"] = state["vehicle_id"]
                output = fn(**args)
            except TypeError as exc:
                output = f"Error: bad arguments for '{call['name']}': {exc}"
        tool_messages.append(
            ToolMessage(content=output, name=call["name"], tool_call_id=call["id"])
        )
    return {"messages": tool_messages}


def _route(state: AgentState) -> str:
    """After `chat`, go to `tools` if the model asked for one, else finish."""
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("chat", chat_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "chat")
    graph.add_conditional_edges("chat", _route, {"tools": "tools", END: END})
    graph.add_edge("tools", "chat")
    return graph.compile()


# Compiled at import so the API layer shares one instance.
graph = build_graph()