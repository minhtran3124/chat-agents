# LangChain Deep Agents — Review Notes

**Sources:**
- [Deep Agents — LangChain docs (Python)](https://docs.langchain.com/oss/python/deepagents/overview)
- [`langchain-ai/deepagents` — GitHub](https://github.com/langchain-ai/deepagents)
- *LangChain Just Released Deep Agents and It Changes How You Build AI Systems* — Towards AI

**Date reviewed:** 2026-04-13
**Applies to:** deepagents 0.5+ (middleware + backend API)

---

## TL;DR

`deepagents` is LangChain's opinionated harness on top of LangGraph. It bundles four production-grade agent patterns — **planning, filesystem access, subagent delegation, and context management** — as *middleware* that plugs into a compiled LangGraph state graph. You choose a *backend* (state, filesystem, store, or a composite) for where the agent's "files" actually live.

The result is a `CompiledStateGraph` — so everything LangGraph gives you (streaming, checkpointing, interrupts, time-travel) still applies, and `agent.astream(..., stream_mode=[...])` is the integration point for SSE UIs like the one in this repo.

> *"The same core tool-calling loop as other frameworks, but with a set of built-in capabilities baked in."*

---

## The Problem It Solves

The typical progression for teams using LangChain:

1. Start with simple **LangChain chains**.
2. Graduate to **LangGraph** when tasks need tool calling + looping.
3. Realize LangGraph is a *low-level runtime* — you hand-write state schemas, conditional edges, and compilation before touching the actual business problem.

Deep Agents is the "opinionated defaults" layer that saves teams from re-engineering the same context management, subagent orchestration, and memory patterns over and over.

---

## Architecture — Three Layers

```
┌───────────────────────────────────────────┐
│  Deep Agents  (harness, defaults)          │
│    ├─ PlanningMiddleware     (write_todos) │
│    ├─ FilesystemMiddleware   (ls/read/…)   │
│    ├─ SubAgentMiddleware     (task tool)   │
│    └─ SummarizationMiddleware (compaction)  │
├───────────────────────────────────────────┤
│  LangGraph  (runtime)                      │
│    persistence · streaming · interrupts    │
├───────────────────────────────────────────┤
│  LangChain  (building blocks)              │
│    models · tools · prompts                │
└───────────────────────────────────────────┘
```

Everything above LangGraph is **middleware composed into a `CompiledStateGraph`**. Each middleware adds tools to the agent and optional hooks into the model-call lifecycle.

---

## Core Capabilities

| # | Capability | Delivered By |
|---|---|---|
| 1 | **Planning (`write_todos`)** | `PlanningMiddleware` — agent auto-decomposes a task into a todo list, updates statuses, and the list persists across the whole session. |
| 2 | **Filesystem (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`)** | `FilesystemMiddleware` + a pluggable **backend** (see below). Large tool outputs are auto-offloaded when they exceed `tool_token_limit_before_evict` (default ~20k tokens). |
| 3 | **Subagent Spawning (`task` tool)** | `SubAgentMiddleware` — delegate isolated subtasks to specialized subagents with clean contexts, tool subsets, and their own model. |
| 4 | **Automatic Context Compression** | `SummarizationMiddleware` — near context-limit, the harness summarizes older messages into a structured note, preserving originals to the filesystem. |
| 5 | **Cross-conversation Memory** | `StoreBackend` + LangGraph checkpointer, or AGENTS.md files loaded via the `memory=[...]` param. |

Filesystem tool paths are always absolute (must start with `/`). Backends decide what "absolute" means — virtual prefix, real disk root, or Store namespace.

---

## Minimal Code Example

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[get_weather],
    system_prompt="You are a helpful assistant",
)
```

Research-agent example with subagents + real filesystem + memory:

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[internet_search],
    system_prompt="You are an expert researcher…",
    memory=[
        "~/.deepagents/AGENTS.md",   # user preferences
        "./.deepagents/AGENTS.md",   # project-specific context
    ],
    subagents=[
        {
            "name": "researcher",
            "description": "Deep-dive a single sub-topic.",
            "model": "anthropic:claude-haiku-4-5",
            "system_prompt": "You are a focused researcher…",
            "tools": [internet_search],
        },
    ],
    backend=FilesystemBackend(root_dir="./workspace"),
)

result = agent.invoke({
    "messages": [{"role": "user", "content": "Research agentic AI frameworks…"}]
})
```

The returned object is a **`CompiledStateGraph`** — sync (`invoke`) and async (`ainvoke`, `astream`) both work.

---

## Backends (pick one or compose)

| Backend | Scope | Use when |
|---|---|---|
| `StateBackend` (default) | Conversation-scoped — files live inside the graph state dict. | Short sessions; no persistence needed. |
| `FilesystemBackend(root_dir=…, virtual_mode=…)` | Real disk, optional virtual-prefix isolation. | Agent should read/write real project files, or persist beyond a single run. |
| `StoreBackend` | LangGraph `Store` (e.g. SQLite, Postgres, Redis impl). | Cross-thread / cross-user persistence; long-term memories. |
| `CompositeBackend(default=…, routes={"/memories/": StoreBackend()})` | Routes paths to different backends. | E.g. `/memories/` → Store, everything else → State. |

```python
from deepagents.backends import CompositeBackend, StateBackend
from deepagents.backends.store import StoreBackend

backend = CompositeBackend(
    default=StateBackend,
    routes={"/memories/": StoreBackend()},
)
```

---

## Streaming with LangGraph (what this project uses)

Because `create_deep_agent` returns a `CompiledStateGraph`, LangGraph streaming applies 1:1:

```python
async for mode, chunk in agent.astream(
    {"messages": [{"role": "user", "content": question}]},
    config={"configurable": {"thread_id": "default-user"}},
    stream_mode=["values", "messages", "updates"],
):
    ...
```

| `stream_mode` | Emits | What the UI uses it for |
|---|---|---|
| `values` | Full state snapshot after each step | Detect compression by diffing token totals. |
| `messages` | `(AIMessageChunk, metadata)` — token-level deltas | Render the model's reply progressively (`text_delta` SSE). |
| `updates` | Per-node update dict: `{node_name: update}` | Turn into `todo_updated`, `file_saved`, `subagent_started/completed` SSE events. |

**Gotcha:** `stream_mode="messages"` only emits token-level chunks if the underlying model has streaming enabled. Pass `streaming=True` to `init_chat_model(...)` (or `ChatAnthropic(..., streaming=True)`) or you'll get one big `AIMessage` per node instead of per-token deltas. *(This caused a 22-second UI stall in this repo before the fix in `apps/api/app/services/llm_factory.py`.)*

---

## How This Project Uses Deep Agents

Wiring lives at `apps/api/app/services/agent_factory.py:37-71`:

- **Model:** `init_chat_model(..., streaming=True)` — main LLM (Sonnet) for the planner, fast LLM (Haiku) for subagents.
- **Tools:** `internet_search` (Tavily) on both main and `researcher` subagent.
- **Subagents:** `researcher` (spawns 2-4 searches, returns 150-word summary), `critic` (reviews draft on VFS, no tools).
- **Memory / Store:** `get_store()` + `get_checkpointer()` — SQLite-backed (`settings.CHECKPOINT_DB_PATH`). Used for `namespace="preferences"` and `namespace="topics"`.
- **Streaming → SSE:** `app/streaming/chunk_mapper.py` translates the three `stream_mode` channels into the typed events defined in `app/streaming/events.py`. FE consumes them via `apps/web/lib/useResearchStream.ts`.

The `default-user` thread ID is hardcoded in the router (`research.py:24`) — a deliberate simplification for MVP; swap for Clerk-user-ID when auth lands.

---

## When to Use vs. When NOT to Use

**Use Deep Agents when:**
- Tasks need multi-step planning.
- Tool results are large and need filesystem offloading.
- You need long-running sessions with persistent memory across threads.
- Research automation, financial analysis, coding workflows with custom skills.

**Do NOT use it when:**
- You want a simple ReAct-style agent → use `langchain.agents.create_agent` directly.
- You need fine-grained graph control → drop to raw LangGraph.

The library's own guidance: *"for simpler agents, use simpler tools."*

---

## Tradeoffs

- **Gain:** convention over configuration — teams stop re-inventing the same infrastructure, and compose real production features (human-in-loop approval, persistent memory, skill loading) through standard middleware.
- **Cost:** opinionated abstraction. Custom loops, unusual state schemas, or non-`CompiledStateGraph` return types need raw LangGraph.
- **Cost:** pre-1.0 surface area. Package is moving fast — pin the exact version in `pyproject.toml`.

---

## Answers to the Original Open Questions

> **How does the 20k-token offload threshold interact with provider-specific context windows (Claude 200k / 1M)?**
The threshold is a **per-tool-result eviction limit** (`tool_token_limit_before_evict=20000`), not a global context ceiling. Big single tool outputs get moved to the FS regardless of headroom. Global compaction is separate (`SummarizationMiddleware`, triggered near context-limit).

> **Can the virtual filesystem backend be swapped for Redis?**
Yes — via `StoreBackend` backed by a Redis `Store` implementation, or as a route in `CompositeBackend`. Today's builtins are State / Filesystem / Store; a Redis Store backing is up to you to wire, but the interface is stable.

> **How does `write_todos` compare to Claude Code's task tracking?**
Same mental model — it's a structured todo-list maintained by the model, visible as state. The tool name and UX diverge, but the intent (plan → tick → adapt) matches.

> **Is `create_deep_agent` compatible with non-Anthropic providers?**
Yes, first-class. Pass any `init_chat_model`-compatible string (`"openai:gpt-4o"`, `"google_genai:gemini-1.5-pro"`) or a pre-built LangChain `BaseChatModel`. Each subagent can run on a different provider.

---

## Follow-ups to Explore

- Try `CompositeBackend(default=StateBackend, routes={"/memories/": StoreBackend()})` in this project — would let user preferences persist across threads without changing the rest of the state handling.
- Evaluate `FilesystemMiddleware(backend=FilesystemBackend(root_dir="./workspace"))` for saving the full draft + critique to disk, not just state, so the UI can let the user download the report.
- Wire `AGENTS.md` into `memory=[...]` so project-specific conventions live in version control.
- Consider `fine-grained-tool-streaming-2025-05-14` beta header on `ChatAnthropic` if tool-call argument streaming ever becomes a latency bottleneck.
