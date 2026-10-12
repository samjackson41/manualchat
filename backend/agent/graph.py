"""Minimal LangGraph agent — the iteration point for ManualChat.

Deliberately skeletal: a single `chat` node and an empty, reserved `tools`
list. The *shape* (StateGraph + AgentState + tools list) is the deliverable
here, not the logic — nodes/tools get added later without rework.

WHERE THE NEXT CHANGES GO (documented so the structure is obviously extensible):

  1. System prompt  -> add a `system` message at the head of `messages` before
     the first `chat` call (no new node needed).

  2. Tool calling   -> append tool schemas to `tools` (below), bind them to the
     model call in `llm.chat`, and add a conditional loop `chat -> tool -> chat`
     so the model can call a tool and resume. One extra node + one conditional
     edge; AgentState is unchanged.

  3. RAG            -> add `search_manual` / `extract_specs` / `get_page_text`
     tools per IMPLEMENTATION Task 4. They land in the SAME `tools` list; the
     graph gains one tool-executor node (see #2). No rework of AgentState.

  4. Memory         -> add a `summary` field + compaction node (MEMORY_DESIGN
     §4-5) and a checkpointer (InMemorySaver, later RedisSaver).
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from backend import llm

# Reserved — empty for now. Tools get appended here when they land (see notes
# above). Keeping this an explicit module-level list is the extension seam.
tools: list = []


class AgentState(TypedDict):
    """Graph state.

    `messages` is the conversation (an Annotated list so LangGraph merges
    node outputs with `add_messages`). `model` is a per-request override of the
    config default — DECISIONS M3 (session-scoped runtime override).
    """

    messages: Annotated[list[BaseMessage], add_messages]
    model: str


_ROLE_MAP = {"human": "user", "ai": "assistant", "system": "system"}


def _serialize(messages: list[BaseMessage]) -> list[dict]:
    """Convert langchain messages to OpenAI chat format for the LLM wrapper."""
    out: list[dict] = []
    for message in messages:
        role = _ROLE_MAP.get(getattr(message, "type", "human"), "user")
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        out.append({"role": role, "content": content})
    return out


def chat_node(state: AgentState) -> dict:
    """Call OpenRouter and append the assistant's reply to `state["messages"]`."""
    reply = llm.chat(_serialize(state["messages"]), state["model"])
    return {"messages": [AIMessage(content=reply)]}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("chat", chat_node)
    graph.add_edge(START, "chat")
    graph.add_edge("chat", END)
    return graph.compile()


# Compiled at import so the API layer shares one instance.
graph = build_graph()