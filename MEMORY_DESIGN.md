# MEMORY DESIGN — conversation memory + summarization (ManualChat)

> Decision record. Captures the "keep Redis in the MVP + add conversation
> summarization" decision, the enabling Redis module requirement, and the
> short-term / long-term memory architecture. Companion to `project_proposal.md`
> (see the "Session Memory" row of its architecture table).

---

## 1. Decisions (locked)

| # | Decision | Why |
|---|---|---|
| D1 | **Keep Redis memory in the MVP**, not just post-MVP | The existing tier is sufficient (size math in §2); durable state is table-stakes for follow-up repair conversations. The original proposal listed `RedisSaver` but left the deployment open — this closes it. |
| D2 | **Add conversation summarization**, with *two* triggers: automatic at a token threshold **and** a manual "Compact" button | Cost/context-window control (auto) + a user-visible, user-controlled lever that is safe mid-repair (manual). |
| D3 | **Split short-term vs. long-term memory**; never summarize extracted facts | ManualChat "does not guess." Summarizing away a torque value or page citation is a correctness bug, not a UX nicety. |
| D4 | **Implement summary + rolling buffer**, not naive truncation | Naive truncation silently drops context and citations; summary+buffer is the correct, interview-defensible pattern. |

---

## 2. Why the existing Redis tier is sufficient (size math)

Redis Cloud **Essentials / AWS us-east-1 / 250 MB / $6/mo**, shared deployment, single DB.

- LangGraph checkpoints serialize the full graph state (messages + retrieved tool
  context). With this project's tools (`search_manual`, `extract_specs`,
  `get_page_text`) a checkpoint is roughly **10–50 KB**, and a turn writes a handful
  (one per super-step + pending writes).
- A genuinely long ~30-turn conversation ≈ **1–3 MB** total.
- ⇒ **250 MB ≈ 80–250+ long conversations.** RAM is *not* the binding constraint.

**The real Essentials limits** (not size): single database, shared CPU, a connection
cap, and **cross-cloud latency** (tier is on AWS us-east-1 while the app stack — Cloud
Run + Qdrant Cloud — is on GCP). All fine for a single-user MVP.

### The one fact that makes RedisSaver work

`langgraph-checkpoint-redis` (**0.5.2**) **requires RedisJSON + RediSearch** modules and
fails on `setup()` if they are absent:

- **Redis 8.0+** → both modules bundled in core Redis (no extra install).
- **Redis < 8.0** → need Redis Stack (or install modules separately).

Redis Cloud runs Redis Enterprise under the hood, which bundles both modules, so the
Essentials tier *should* expose them. **Verify with this canary** before committing:

```
JSON.SET k . '{}'
FT.CREATE idx ON JSON SCHEMA $.x AS x NUMERIC
# or simply: saver.setup()  -> errors if modules are missing
```

### Local dev (MVP)

```bash
docker run -d --name redis-memory -p 6379:6379 redis:8.0
# fallback if module issues: redis/redis-stack-server
```

---

## 3. Memory architecture — short-term vs. long-term split

```
              CONVERSATION MEMORY
   ┌──────────────────┬──────────────────────┐
   │ SHORT-TERM       │  LONG-TERM           │
   │ (prose, turns)   │  (facts, specs)      │
   │                  │                      │
   │ compacted into   │  NEVER summarized —  │
   │ rolling summary  │  verbatim, keyed by  │
   │ when over budget │  vehicle + manual    │
   └────────┬─────────┴──────────┬───────────┘
            │ (Redis: state.summary)          │ (the "spec ledger")
            ▼
   "Summarize the conversation.   "Engine oil drain bolt = 30 N·m (p.24)"
```

- **Short-term memory** = recent messages, compacted into a rolling summary.
- **Long-term memory** = the specs/torques/citations that `extract_specs` /
  `search_manual` already return. These are *already structured* — persist them
  verbatim in a **spec ledger** keyed by topic, filtered by the active vehicle
  (reuse the existing Qdrant tag convention). The summarizer **must never touch them**.

This is the property that keeps the agent grounded over long conversations, and it is
the concrete answer to "how does your agent never hallucinate a torque value?"

---

## 4. Summarization — summary + rolling buffer

Keep the last N turns verbatim; summarize only the older turns into a single summary
message. (Full re-summary every turn = slow + drift; naive drop-oldest = loses context.)

### State schema (summary persists via RedisSaver)

```python
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]   # short-term (recent turns)
    summary: str                              # rolling summary, persisted by RedisSaver
    # ... existing fields: vehicle_id, manual_id, page_index, citations
```

### Compaction node (pseudocode)

```
def should_compact(state) -> bool:
    return estimate_tokens(state["messages"]) > THRESHOLD   # e.g. ~60% of context window

def compact(state):
    older, recent = split_messages(state["messages"], keep_last=N)
    new_summary = active_model.invoke(SUMMARIZE_PROMPT(state["summary"], older))
    return {
        "summary": new_summary,
        "messages": [summarize_msg(new_summary)] + recent,   # replace old with one message
    }

# edge: should_compact ? -> compact : -> supervisor
```

### Summarization prompt constraint (project-specific)

> "Summarize the conversation's reasoning and steps, but re-emit any exact numbers,
> units, part names, and page citations **verbatim** — never paraphrase a value."

Values are also held in the spec ledger, but this protects recent-turn facts during the
buffer window before they migrate to the ledger.

### OpenAI / OpenRouter cost

Summarization uses the **active model** — the single UI-selected `models.default` — not a
separate "cheap" tier. Neither trigger costs meaningfully.

---

## 5. Triggers

| Trigger | Mechanism | Endpoint / hook |
|---|---|---|
| **Automatic at n tokens** | token-count the history (`tiktoken` `cl100k_base` as a stable proxy, or the model's tokenizer via OpenRouter); trigger `compact` before the next model call | conditional edge or `pre_model_hook` |
| **Manual "Compact"** | user clicks a button; runs the node; returns the new summary | `POST /chat/compact` (mirrors existing `POST /chat/stream`) |

Manual compact should render the returned summary as a collapsible "conversation so far"
panel in the Next.js chat — visible and user-auditable, not silent rewriting.

---

## 6. Resume-builder framing + evaluation

- **Name it precisely**: "context-window management with a summary + rolling-buffer
  memory architecture and a short-term/long-term split" — not "chat history trimming."
- **The spec ledger is the differentiator** — it is *why* the agent stays grounded, and
  it is the interview-safe answer to groundedness-under-long-conversation.
- **Add one eval metric — "compaction safety"** — to the existing LangSmith pipeline
  (which already judges citation precision, spec accuracy, hallucination rate):

  > After N turns and an auto-compact, does the cited page still contain the fact, and
  > do the numbers still match the source table?

  That single metric turns "I added a summary" into "I proved summarization doesn't
  degrade correctness."

---

## 7. Open items / verify at implementation time

- [ ] Confirm the current LangGraph summarization builder name (likely in `langmem`;
      LangGraph's docs domain redirected during research — patterns here are stable but
      the exact import path should be checked against current docs).
- [ ] Run the RedisJSON/RediSearch canary against the Essentials endpoint before wiring
      `RedisSaver`.
- [ ] Pick the token-counting method (tiktoken proxy vs. model tokenizer) and the exact
      threshold fraction.
- [ ] Define the spec-ledger schema + filter key (vehicle/manual), reusing the existing
      tag convention. Storage is decided: Qdrant metadata payloads (DECISIONS L1).
- [ ] Decide keep_last=N buffer size.