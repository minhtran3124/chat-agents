# Design Spec — Deep Agents Research Assistant (MVP)

**Status:** Approved (iteration 2, one bug fixed post-review)
**Author:** Minh Tran
**Date:** 2026-04-13
**Related notes:** [`2026-04-13-langchain-deep-agents-notes.md`](./2026-04-13-langchain-deep-agents-notes.md)

---

## 1. Goal

Build a **minimum-demo research assistant** that exercises all 5 built-in capabilities of LangChain Deep Agents:

1. Planning via `write_todos`
2. Virtual filesystem (context offloading)
3. Subagent spawning
4. Automatic context compression
5. Cross-conversation memory

Each capability must be **visible to the user on a dashboard UI** — this demo's purpose is to show the capabilities, not just use them silently.

## 2. Non-Goals

- Authentication / multi-user (single default user)
- Production deployment (local-only)
- Full persistent storage beyond SQLite checkpointer (no Postgres, no Redis)
- File upload / PDF parsing
- Rate limiting, quota, billing

## 3. Stack

| Layer | Technology | Version pin |
|---|---|---|
| Runtime | Python 3.11+ | — |
| Web framework | FastAPI | `>=0.115,<0.120` |
| Agent harness | `deepagents` | pin exact at install, e.g. `==0.0.20` (package is pre-1.0, moving fast) |
| Graph runtime | `langgraph` | `>=0.2.70,<0.3` |
| LLM client | `langchain` + `langchain-anthropic` / `-openai` / `-google-genai` | `langchain>=0.3.15,<0.4` |
| LLM default | Anthropic Claude Sonnet 4.6 (`claude-sonnet-4-6`), swappable via settings | — |
| Search tool | Tavily (`tavily-python`) | `>=0.5,<1.0` |
| Checkpointer | `langgraph-checkpoint-sqlite` (`AsyncSqliteSaver`) | `>=2.0,<3.0` |
| Cross-thread store | `InMemoryStore` (upgrade to `langgraph-store-sqlite` when pinned version ships it stable) | — |
| Streaming | Server-Sent Events via `sse-starlette` | `>=2.1,<3.0` |
| Frontend | Next.js 14 (App Router) + TypeScript + Tailwind | `next@^14.2` |

Version pins go in `apps/api/pyproject.toml` and `apps/web/package.json`. Lock files committed.

## 4. Project Structure

```
chat-agents/
├── apps/
│   ├── api/                              # FastAPI backend
│   │   ├── app/
│   │   │   ├── main.py                   # entry, lifespan, CORS, router registration
│   │   │   ├── config/
│   │   │   │   └── settings.py           # Pydantic Settings (LLM_PROVIDER, keys, paths)
│   │   │   ├── routers/
│   │   │   │   └── research.py           # POST /research — SSE stream
│   │   │   ├── services/
│   │   │   │   ├── llm_factory.py        # provider-agnostic LLM builder
│   │   │   │   ├── agent_factory.py      # create_deep_agent() + subagents + tools
│   │   │   │   └── search_tool.py        # Tavily wrapper as LangChain tool
│   │   │   ├── schemas/
│   │   │   │   └── research.py           # Pydantic I/O models
│   │   │   ├── stores/
│   │   │   │   └── memory_store.py       # LangGraph Store + AsyncSqliteSaver
│   │   │   └── streaming/
│   │   │       ├── events.py             # SSE event helpers (10 event types)
│   │   │       └── chunk_mapper.py       # LangGraph chunk → SSE event reducer
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   ├── integration/
│   │   │   └── e2e/
│   │   ├── .env.example
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── web/                              # Next.js frontend
│       ├── app/
│       │   ├── research/
│       │   │   ├── page.tsx              # dashboard
│       │   │   └── components/
│       │   │       ├── QuestionForm.tsx
│       │   │       ├── TodoList.tsx
│       │   │       ├── FileList.tsx
│       │   │       ├── SubagentPanel.tsx
│       │   │       ├── CompressionBadge.tsx
│       │   │       └── ReportView.tsx
│       │   └── api/
│       │       └── research/
│       │           └── route.ts          # SSE proxy to FastAPI
│       ├── lib/
│       │   └── useResearchStream.ts      # EventSource hook + reducer
│       ├── package.json
│       └── README.md
└── docs/
    └── 2026-04-13-deep-agents-research-assistant-design.md
```

---

## 5. Section 1 — Settings & LLM Factory

Provider-agnostic config. Swap LLM = edit `.env`, no code changes.

**`app/config/settings.py`**

```python
from typing import Literal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_DEFAULT_MODEL = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "google": "gemini-1.5-pro",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LLM_PROVIDER: Literal["anthropic", "openai", "google"] = "anthropic"
    LLM_MODEL: str | None = None  # resolved to provider default if unset

    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None

    TAVILY_API_KEY: str = Field(..., description="Required for research tool")

    CHECKPOINT_DB_PATH: str = "./data/checkpoints.sqlite"
    VFS_OFFLOAD_THRESHOLD_TOKENS: int = 20_000

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def _resolve_and_validate(self):
        # Resolve LLM_MODEL default matched to provider — prevents the classic
        # bug of LLM_PROVIDER=openai + leftover LLM_MODEL=claude-sonnet-4-6.
        if self.LLM_MODEL is None:
            object.__setattr__(self, "LLM_MODEL", _DEFAULT_MODEL[self.LLM_PROVIDER])

        key_map = {
            "anthropic": self.ANTHROPIC_API_KEY,
            "openai": self.OPENAI_API_KEY,
            "google": self.GOOGLE_API_KEY,
        }
        if not key_map[self.LLM_PROVIDER]:
            raise ValueError(
                f"LLM_PROVIDER={self.LLM_PROVIDER} but "
                f"{self.LLM_PROVIDER.upper()}_API_KEY is missing"
            )
        return self


settings = Settings()
```

**`app/services/llm_factory.py`**

```python
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.config.settings import settings

_FAST_MODEL = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "google": "gemini-1.5-flash",
}


def get_llm() -> BaseChatModel:
    return init_chat_model(
        model=settings.LLM_MODEL,
        model_provider=settings.LLM_PROVIDER,
    )


def get_fast_llm() -> BaseChatModel:
    return init_chat_model(
        model=_FAST_MODEL[settings.LLM_PROVIDER],
        model_provider=settings.LLM_PROVIDER,
    )
```

**`.env.example`**

```bash
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-6

ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=...

TAVILY_API_KEY=tvly-...
```

**To switch LLM:** edit `.env`, restart backend. No code changes.

---

## 6. Section 2 — Agent Factory (5 Capabilities Wired)

| # | Capability | Wired by |
|---|---|---|
| 1 | Planning (`write_todos`) | Built-in Deep Agents default |
| 2 | Virtual Filesystem | Built-in state-based (in-memory, per session) |
| 3 | Subagents | `subagents=[researcher, critic]` param |
| 4 | Auto-compression | Built-in at ~85% context |
| 5 | Cross-conv memory | `store=get_store()` + `checkpointer=...` |

**`app/services/search_tool.py`**

```python
from langchain_core.tools import tool
from tavily import TavilyClient

from app.config.settings import settings

_tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)


@tool
def internet_search(
    query: str,
    max_results: int = 5,
    topic: str = "general",
    include_raw_content: bool = False,
) -> dict:
    """Search the web for up-to-date information on a topic."""
    return _tavily.search(
        query=query,
        max_results=max_results,
        topic=topic,
        include_raw_content=include_raw_content,
    )
```

**`app/services/agent_factory.py`**

```python
from deepagents import create_deep_agent, SubAgent

from app.services.llm_factory import get_llm, get_fast_llm
from app.services.search_tool import internet_search
from app.stores.memory_store import get_store, get_checkpointer

RESEARCHER_PROMPT = """You are a focused researcher. For ONE topic given by the main agent:
- Run 2-4 targeted searches.
- Save raw results to virtual filesystem.
- Return a concise 150-word summary with citations (URL + quote).
Do NOT write the final report — the main agent does that."""

CRITIC_PROMPT = """You are a skeptical critic. Read the draft report from virtual FS and:
- Flag unsupported claims (no citation).
- Flag outdated info (>2 years old unless historical).
- Flag contradictions between sources.
Return a bulleted list of issues. Do NOT rewrite."""

MAIN_PROMPT = """You are an expert research assistant. Given a research question:

1. Use `write_todos` to break the question into 3-5 sub-topics.
2. Read user preferences from the store (namespace="preferences").
3. For each sub-topic, spawn the `researcher` subagent with a specific focus.
4. Synthesize findings into a draft report saved to virtual FS as `draft.md`.
5. Spawn the `critic` subagent to review the draft.
6. Revise based on critic feedback, then output the final markdown report.
7. After answering, update the store:
     - Append this topic to namespace="topics".
     - If the user expressed a preference (tone, depth, citation style), update namespace="preferences".

Always cite sources inline as [1], [2], … with a References section at the end."""


def build_research_agent():
    main_llm = get_llm()
    fast_llm = get_fast_llm()

    subagents = [
        SubAgent(
            name="researcher",
            description=(
                "Deep-dive a single sub-topic: run searches, save raw results, "
                "return 150-word summary with citations."
            ),
            prompt=RESEARCHER_PROMPT,
            tools=[internet_search],
            model=fast_llm,
        ),
        SubAgent(
            name="critic",
            description=(
                "Review the draft report on virtual FS and list issues "
                "(unsupported claims, outdated info, contradictions)."
            ),
            prompt=CRITIC_PROMPT,
            tools=[],
            model=fast_llm,
        ),
    ]

    return create_deep_agent(
        model=main_llm,
        tools=[internet_search],
        subagents=subagents,
        system_prompt=MAIN_PROMPT,
        store=get_store(),
        checkpointer=get_checkpointer(),
    )
```

### Flow (end-to-end)

```
User: "Compare 3 agentic AI frameworks"
 │
 ├─ [#1] write_todos → [Research LangGraph, Research CrewAI, Research AutoGen, Write report, Critic review]
 ├─ [#5] Read store("preferences", "default-user") → {tone: "concise", citation_style: "inline"}
 ├─ [#3] Spawn researcher × 3 in parallel
 │        each: search web → [#2] save raw results >20k to vfs → 150-word summary
 ├─ Main agent synthesizes → saves vfs://draft.md
 ├─ [#3] Spawn critic → reads vfs://draft.md → returns issue list
 ├─ Main agent revises → streams final report (text_delta events)
 ├─ [#4] If context >85%, harness auto-compresses (transparently)
 └─ [#5] Store update: topics += ["agentic AI frameworks"]
```

---

## 7. Section 3 — SSE Streaming Protocol

**Transport:** `sse-starlette.EventSourceResponse`. Each chunk is JSON with a named `event:` field.

| Event | Payload | Trigger | Capability |
|---|---|---|---|
| `stream_start` | `{thread_id, started_at}` | Stream opens | — |
| `todo_updated` | `{items: [{text, status}]}` | Agent calls `write_todos` | Planning |
| `file_saved` | `{path, size_tokens, preview}` | Agent writes to vFS | Virtual FS |
| `subagent_started` | `{id, name, task}` | Subagent spawned | Subagent |
| `subagent_completed` | `{id, summary}` | Subagent returns | Subagent |
| `compression_triggered` | `{original_tokens, compressed_tokens}` | Harness auto-compresses | Compression |
| `text_delta` | `{content}` | Final report streaming | — |
| `memory_updated` | `{namespace, key}` | Store write | Memory |
| `error` | `{message, recoverable}` | Any exception | — |
| `stream_end` | `{final_report, usage}` | Stream closes | — |

**`app/streaming/events.py`**

```python
import json
from datetime import datetime, timezone
from typing import Any


def _sse(event: str, data: dict) -> dict:
    """sse-starlette expects dict with 'event' and 'data' (stringified)."""
    return {"event": event, "data": json.dumps(data, default=str)}


def stream_start(thread_id: str) -> dict:
    return _sse("stream_start", {
        "thread_id": thread_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })


def todo_updated(items: list[dict]) -> dict:
    # items: [{"text": str, "status": "pending|in_progress|done"}]
    return _sse("todo_updated", {"items": items})


def file_saved(path: str, size_tokens: int, preview: str) -> dict:
    return _sse("file_saved", {
        "path": path, "size_tokens": size_tokens, "preview": preview[:500],
    })


def subagent_started(run_id: str, name: str, task: str) -> dict:
    return _sse("subagent_started", {"id": run_id, "name": name, "task": task})


def subagent_completed(run_id: str, summary: str) -> dict:
    return _sse("subagent_completed", {"id": run_id, "summary": summary})


def compression_triggered(original_tokens: int, compressed_tokens: int) -> dict:
    return _sse("compression_triggered", {
        "original_tokens": original_tokens,
        "compressed_tokens": compressed_tokens,
    })


def text_delta(content: str) -> dict:
    return _sse("text_delta", {"content": content})


def memory_updated(namespace: str, key: str) -> dict:
    return _sse("memory_updated", {"namespace": namespace, "key": key})


def error(message: str, recoverable: bool = False) -> dict:
    return _sse("error", {"message": message, "recoverable": recoverable})


def stream_end(final_report: str, usage: dict[str, Any]) -> dict:
    return _sse("stream_end", {"final_report": final_report, "usage": usage})
```

### Stream chunk → SSE event mapping

LangGraph's `astream(stream_mode=["values","messages","updates"])` yields tuples `(mode, chunk)`. Mapping rules:

| Chunk source | Detect via | Emitted SSE event |
|---|---|---|
| `updates` where key = `"todos"` | presence of `todos` delta | `todo_updated` with full list from the value |
| `updates` where key = `"files"` (vFS state) | new/changed entries in files dict vs. previous snapshot | `file_saved` per new/changed path; `size_tokens` via `len(tokenizer.encode(content))`; preview = content[:500] |
| `updates` where key = a subagent node name | node start/end edges | `subagent_started` on first appearance; `subagent_completed` on terminal state (with summary = last AIMessage content) |
| `messages` with AIMessageChunk from main agent | chunk has `content` text | `text_delta` — only after main agent reaches the final-report phase (tracked via state flag `report_phase=True` set when critic returns) |
| State snapshot (`values` mode) | token count drop ≥ 30% between consecutive snapshots | `compression_triggered` (heuristic — see Section 10) |
| Store write (from agent callback) | custom callback listening to store mutations | `memory_updated` |

**Module responsible for this mapping:** `app/streaming/chunk_mapper.py`

**Module-private helpers** referenced below:
- `_count_tokens(text)` — uses `tiktoken.encoding_for_model("gpt-4o")` (provider-agnostic approximation) and returns `len(tokens)`.
- `_new_id()` — returns `uuid.uuid4().hex`.
- `_estimate_state_tokens(snapshot)` — sums `_count_tokens(...)` across `snapshot["messages"]` content and `snapshot["files"]` values.

```python
from typing import AsyncIterator, Any
from langgraph.pregel import Pregel

from app.streaming import events


class ChunkMapper:
    """Stateful mapper that diffs LangGraph chunks against prior state to emit SSE events."""

    def __init__(self) -> None:
        self._prev_files: dict[str, str] = {}
        self._prev_todos: list[dict] = []
        self._active_subagents: dict[str, str] = {}   # node_name -> run_id
        self._prev_token_count: int | None = None
        self._report_phase: bool = False

    async def process(self, mode: str, chunk: Any) -> AsyncIterator[dict]:
        if mode == "updates":
            async for ev in self._handle_updates(chunk):
                yield ev
        elif mode == "messages":
            msg_chunk, meta = chunk
            if self._report_phase and getattr(msg_chunk, "content", ""):
                yield events.text_delta(msg_chunk.content)
        elif mode == "values":
            async for ev in self._handle_values_snapshot(chunk):
                yield ev

    async def _handle_updates(self, chunk: dict) -> AsyncIterator[dict]:
        for node_name, update in chunk.items():
            if "todos" in update and update["todos"] != self._prev_todos:
                self._prev_todos = update["todos"]
                yield events.todo_updated(update["todos"])
            if "files" in update:
                for path, content in update["files"].items():
                    if self._prev_files.get(path) != content:
                        self._prev_files[path] = content
                        yield events.file_saved(
                            path=path,
                            size_tokens=_count_tokens(content),
                            preview=content[:500],
                        )
            if node_name in {"researcher", "critic"}:
                # subagent lifecycle — Deep Agents exposes subagent node names
                run_id = self._active_subagents.get(node_name) or _new_id()
                if node_name not in self._active_subagents:
                    self._active_subagents[node_name] = run_id
                    yield events.subagent_started(
                        run_id, node_name, update.get("task", "")
                    )
                elif update.get("__end__") or update.get("summary"):
                    yield events.subagent_completed(
                        run_id, update.get("summary", "")
                    )
                    del self._active_subagents[node_name]
                if node_name == "critic":
                    self._report_phase = True

    async def _handle_values_snapshot(self, snapshot: dict) -> AsyncIterator[dict]:
        current = _estimate_state_tokens(snapshot)
        if self._prev_token_count and current < self._prev_token_count * 0.7:
            yield events.compression_triggered(self._prev_token_count, current)
        self._prev_token_count = current
```

**`app/routers/research.py`**

```python
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.schemas.research import ResearchRequest
from app.services.agent_factory import build_research_agent
from app.streaming import events
from app.streaming.chunk_mapper import ChunkMapper

router = APIRouter(prefix="/research", tags=["research"])


@router.post("")
async def research(payload: ResearchRequest):
    agent = build_research_agent()
    thread_id = payload.thread_id or "default-user"
    mapper = ChunkMapper()
    final_report_parts: list[str] = []

    async def generator():
        yield events.stream_start(thread_id)
        try:
            async for mode, chunk in agent.astream(
                {"messages": [{"role": "user", "content": payload.question}]},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode=["values", "messages", "updates"],
            ):
                async for ev in mapper.process(mode, chunk):
                    if ev["event"] == "text_delta":
                        final_report_parts.append(
                            json.loads(ev["data"])["content"]
                        )
                    yield ev
            # Read final state from checkpointer for usage
            final_state = await agent.aget_state(
                {"configurable": {"thread_id": thread_id}}
            )
            usage = final_state.values.get("usage", {})
            yield events.stream_end(
                final_report="".join(final_report_parts),
                usage=usage,
            )
        except Exception as e:
            yield events.error(str(e), recoverable=False)

    return EventSourceResponse(generator())
```

---

## 8. Section 4 — Frontend Dashboard

**Route:** `/research` (single page, no auth).

**Component tree**

```
<page.tsx>
  <QuestionForm onSubmit={start} />            // POST /api/research
  <Dashboard>
    <LeftColumn>
      <TodoList        items={state.todos}         />  // todo_updated
      <FileList        files={state.files}         />  // file_saved
      <SubagentPanel   runs={state.subagents}      >   // subagent_started/completed
        <CompressionBadge count={state.compressions.length} /> // compression_triggered
      </SubagentPanel>
    </LeftColumn>
    <RightColumn>
      <ReportView      text={state.report}          /> // text_delta
    </RightColumn>
  </Dashboard>
```

`CompressionBadge` renders inside `SubagentPanel` to match the ASCII layout below.

**`lib/useResearchStream.ts`** (hook contract)

```ts
type ResearchState = {
  todos: TodoItem[];
  files: FileRef[];
  subagents: Map<string, SubagentRun>;
  compressions: CompressionEvent[];
  report: string;
  status: "idle" | "streaming" | "done" | "error";
};

export function useResearchStream(): {
  state: ResearchState;
  start: (question: string) => void;
  stop: () => void;
}
```

**Transport note — why NOT `EventSource`:** native `EventSource` is GET-only with no body. Our backend is `POST /research` with a JSON payload (question, thread_id). We instead use `fetch` with a `ReadableStream` and a custom SSE parser. This is a small (~30-line) helper but is the standard pattern for streaming POST endpoints.

```ts
// Inside useResearchStream.ts — pseudocode sketch.
// `consumeFrames` / `leftoverAfterFrames` / `dispatch` are ~30 lines of
// real SSE frame parsing (split on "\n\n", parse "event:" and "data:" lines).
// Budget this as a small utility module during implementation.
async function start(question: string) {
  controller.current = new AbortController();
  const res = await fetch("/api/research", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ question, thread_id: "default-user" }),
    signal: controller.current.signal,
  });
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames separated by "\n\n"; parse event: / data: lines
    for (const frame of consumeFrames(buffer)) {
      dispatch(frame);                        // reducer update
    }
    buffer = leftoverAfterFrames(buffer);
  }
}

function stop() {
  controller.current?.abort();                 // closes stream; backend gets CancelledError
}
```

Reducer pattern: each event type maps to one state mutation. Dispatch table `{stream_start, todo_updated, file_saved, subagent_started, subagent_completed, compression_triggered, text_delta, memory_updated, error, stream_end}`.

**`app/api/research/route.ts`** — thin proxy so browser doesn't need CORS/key mgmt:

```ts
export async function POST(req: Request) {
  const body = await req.text();
  const upstream = await fetch(`${process.env.API_URL}/research`, {
    method: "POST",
    body,
    headers: { "content-type": "application/json" },
  });
  return new Response(upstream.body, {
    headers: { "content-type": "text/event-stream", "cache-control": "no-cache" },
  });
}
```

**Visual layout (ASCII)**

```
┌─ Research Assistant ──────────────────────────────────────────┐
│ [Ask a research question...................] [Start]         │
├───────────────────┬──────────────────────────────────────────┤
│ 📋 To-do          │  📄 Final Report (streaming)             │
│   ✓ Research LG   │                                           │
│   ✓ Research CA   │  # Agentic AI Frameworks: A Comparison    │
│   ⏳ Write report  │  ...                                       │
├───────────────────┤                                           │
│ 📁 Files (vFS)    │                                           │
│   langraph.md 35k │                                           │
│   crewai.md   28k │                                           │
│   draft.md     4k │                                           │
├───────────────────┤                                           │
│ 🤖 Subagents      │                                           │
│   researcher×3 ✓  │                                           │
│   critic       ⏳ │                                           │
│ 🗜  2 compressions │                                           │
└───────────────────┴──────────────────────────────────────────┘
```

---

## 9. Section 5 — Memory Store (Cross-Conversation)

**Two distinct persistence concerns:**

| Concern | Scope | Backend |
|---|---|---|
| **Checkpointer** | Conversation state per thread (messages, todos, vFS) | `AsyncSqliteSaver` over `./data/checkpoints.sqlite` |
| **Store** | Cross-thread user knowledge (preferences, past topics) | `InMemoryStore()` (see upgrade note below) |

**`AsyncSqliteSaver` correct usage:** it is an **async context manager**, not a factory — it must be entered via `async with ... as saver:`. We manage its lifetime in the FastAPI `lifespan`.

**`app/stores/memory_store.py`**

```python
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.memory import InMemoryStore

from app.config.settings import settings

_store = InMemoryStore()
_checkpointer: AsyncSqliteSaver | None = None


@asynccontextmanager
async def lifespan_stores() -> AsyncIterator[None]:
    """Wire into FastAPI lifespan. Opens/closes SQLite connection correctly."""
    global _checkpointer
    Path(settings.CHECKPOINT_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(
        settings.CHECKPOINT_DB_PATH
    ) as cp:
        _checkpointer = cp
        try:
            yield
        finally:
            _checkpointer = None


def get_store() -> InMemoryStore:
    return _store


def get_checkpointer() -> AsyncSqliteSaver:
    if _checkpointer is None:
        raise RuntimeError("Checkpointer not initialized — app lifespan not active")
    return _checkpointer
```

**`app/main.py`** — wire lifespan:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.stores.memory_store import lifespan_stores
from app.routers import research


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with lifespan_stores():
        yield


app = FastAPI(lifespan=lifespan)
app.include_router(research.router)
```

**Namespaces used by the agent:**

- `("preferences", user_id)` — tone, citation style, depth preference
- `("topics", user_id)` — list of past research topics

Thread ID is fixed to `"default-user"` for this single-user demo. The store persists across threads via the same namespace.

**Upgrade path — persistent cross-thread memory:**

`InMemoryStore` loses preferences on restart, which breaks Success Criterion #5 if the user restarts backend between sessions. Two mitigation options ranked by readiness at time of writing:

1. **Preferred:** check whether the pinned `langgraph` version exposes `langgraph.store.sqlite.AsyncSqliteStore`. If yes, swap `InMemoryStore()` for `AsyncSqliteStore.from_conn_string(...)` and add it to the same `lifespan_stores()` async context.
2. **Fallback:** wrap `InMemoryStore` with a thin persistence layer that dumps/loads the store's underlying dict to a JSON file on startup/shutdown. ~40 lines in `memory_store.py`. Good enough for the demo — not for production.

Decision point during implementation: **do option 1 if available, option 2 if not**. Success Criterion #5 requires at minimum option 2.

---

## 9.1 Compression visibility — fallback heuristic

Deep Agents' `astream` may not expose compression as a first-class signal. Our approach:

1. **Primary:** if the `updates` stream emits a node tagged `"compression"` (Deep Agents internal), map directly to `compression_triggered`.
2. **Fallback heuristic (implemented by default):** `ChunkMapper._handle_values_snapshot` tracks estimated token count across `values` mode snapshots. When current < 70% of previous, emit `compression_triggered(previous, current)`. Threshold configurable via `settings.COMPRESSION_DETECTION_RATIO` (default 0.7).
3. **Always emit at least one synthetic `compression_triggered`** near end-of-session if no real compression was detected but session exceeded 30k total tokens — marked with `{synthetic: true}`. **Fired by:** the router generator, after the `astream` loop exits and before `stream_end`, gated on `mapper.saw_compression == False` and `mapper.peak_tokens > 30_000`. `ChunkMapper` exposes both as public attributes. UI shows a tooltip "estimated" when `synthetic=true`.

Cost of this strategy: one field bit (`synthetic`), and honest UX — the badge still informs users that the capability exists.

## 10. Section 6 — Error Handling & Testing

### Error handling

| Scenario | Handling |
|---|---|
| Missing API key for selected provider | `Settings.model_validator` raises at import → backend won't start |
| Tavily 429 / network error | Tool returns error dict → agent continues with partial data → `error` event streamed |
| Claude overload (529) | LangChain built-in retry → if exhausted, emit `error(recoverable=true)` → frontend shows "retry" button |
| Agent interruption (user closes tab) | `EventSource.close()` → backend cancels via context cancellation → partial state saved to checkpointer |
| Uncaught exception mid-stream | Caught in SSE generator → emit `error(recoverable=false)` → stream closes cleanly |

### Testing strategy

**Unit** (`tests/unit/`):
- `test_settings.py` — `LLM_PROVIDER=openai` without `OPENAI_API_KEY` raises
- `test_llm_factory.py` — `get_llm()` returns correct class per provider (mock `init_chat_model`)
- `test_search_tool.py` — Tavily client called with correct kwargs (mock)

**Integration** (`tests/integration/`):
- `test_agent_factory.py` — `build_research_agent()` returns agent with 2 subagents, correct tools, store wired
- Mock `internet_search` returns fixture data → `agent.invoke()` produces report structure

**E2E smoke** (`tests/e2e/`):
- `test_research_endpoint.py` — POST `/research` with short question, assert SSE event order: `stream_start → todo_updated → subagent_started → … → stream_end`
- Uses real Tavily + cheap Haiku model (or cassette-based with VCR.py)

**Coverage target:** 70% (lower than prod services — this is a demo).

---

## 11. Out of Scope (YAGNI)

Explicitly **not** doing in this MVP:

- User authentication
- Multi-user data isolation
- Database beyond SQLite
- Deployment / CI / Docker
- Rate limiting / quota
- Token usage logging / billing
- Conversation history UI (no past sessions list)
- Streaming cancellation UI beyond "close tab"
- File upload / document ingestion
- Mobile-responsive UI

These are legitimate future features but not needed to demonstrate the 5 Deep Agents capabilities.

---

## 12. Success Criteria

Demo is successful if, in one research session, the user can observe:

- [ ] **Planning** — To-do list appears and updates as the agent progresses
- [ ] **Virtual FS** — Files appear in the FileList panel with preview + size
- [ ] **Subagents** — Multiple subagent runs visible in SubagentPanel, with at least 1 parallel run
- [ ] **Compression** — On a long session (>30k tokens), CompressionBadge shows at least 1 trigger
- [ ] **Cross-conv memory** — Starting a second session, agent references prior topic or applies stored preference
- [ ] **LLM swap** — Changing `.env` from `anthropic` to `openai` + restarting → same demo works

## 13. Open Questions / Risks

- **Deep Agents internal API stability** — package is pre-1.0. Subagent node names, state keys (`todos`, `files`), and streaming internals may shift. Pin version; on upgrade, run the E2E smoke test and inspect the first real `astream` chunk sequence against `ChunkMapper` expectations.
- **Memory store persistence** — `InMemoryStore` loses state on restart. Mitigation spec'd in Section 9 (upgrade to `AsyncSqliteStore` if pinned version exposes it; else JSON-dump fallback). Decision deferred to implementation based on version check.
- **Compression detection relies on heuristic** — see Section 9.1. If Deep Agents later exposes a direct compression event, swap to it and remove the heuristic. Synthetic badge exists so Success Criterion #4 is always observable.
- **Subagent node naming assumption** — `ChunkMapper._handle_updates` assumes node names match subagent names (`"researcher"`, `"critic"`). Verify against first real stream during implementation; if Deep Agents prefixes/suffixes names, update the matcher.
- **Tavily cost** — 1000 free req/month; heavy demo iteration may hit limit. Document how to switch to DuckDuckGo as a drop-in replacement tool.

---

## 14. Next Steps

After this design is approved, the next step is the **implementation plan** via the `writing-plans` skill — breaking the work into ordered, testable milestones.
