# Phase 1: LangSmith Tracing + structlog + Token Budget Guard — Design Spec

**Date:** 2026-04-24
**Branch:** to be cut from `main` after Phase 0 merges
**PR target:** `feat(api,web): langsmith tracing + structlog + token budget`
**Depends on:** Phase 0 (`fix/phase-0-stabilize-sse-contract`)
**Issue:** [#3](https://github.com/minhtran3124/chat-agents/issues/3)

---

## 1. Goal

> See every run in LangSmith; cap what any single run can cost.

Three independently useful capabilities shipped together because they share observability infrastructure:

1. **LangSmith tracing** — full supervisor + subagent hierarchy visible per `/research` call
2. **structlog** — all application logs are structured JSON with `request_id`, `thread_id`, `prompt_versions` bound from async context
3. **Token budget guard** — abort runs that exceed `MAX_TOKENS_PER_RUN`; emit a distinct `budget_exceeded` SSE event; surface it in a redesigned inline error UI

---

## 2. Architecture Overview

```
apps/api/app/
├── observability/               ← NEW package
│   ├── __init__.py
│   ├── structlog_setup.py       ← configure structlog once at startup
│   └── middleware.py            ← RequestContextMiddleware: bind request_id per request
├── routers/
│   └── research.py              ← token accumulation, budget abort, structlog calls
├── streaming/
│   └── events.py                ← add budget_exceeded() factory
└── config/
    └── settings.py              ← add MAX_TOKENS_PER_RUN + LANGCHAIN_* optional fields

apps/web/lib/
├── types.ts                     ← add budget_exceeded to SSEEventMap
└── useResearchStream.ts         ← add budgetExceeded state field + reducer case

apps/web/app/research/
├── page.tsx                     ← replace bottom error bar with inline ErrorView
└── components/
    └── ErrorView.tsx            ← NEW: warning (amber) and error (red) variants
```

---

## 3. LangSmith Tracing

### 3.1 Activation

LangChain/LangGraph activates tracing automatically when `LANGCHAIN_TRACING_V2=true` is set in the environment. Because `pydantic-settings` reads `.env` into the model but does **not** set `os.environ` automatically, these keys must be added to `Settings` and re-exported via `model_validator` — exactly the same pattern already used for `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, etc.

New optional fields in `config/settings.py`:

```python
LANGCHAIN_TRACING_V2: str | None = None    # "true" to enable
LANGCHAIN_API_KEY: str | None = None
LANGCHAIN_PROJECT: str | None = None
```

Add to the `model_validator` re-export block:

```python
for env_name, value in [
    ("LANGCHAIN_TRACING_V2", self.LANGCHAIN_TRACING_V2),
    ("LANGCHAIN_API_KEY", self.LANGCHAIN_API_KEY),
    ("LANGCHAIN_PROJECT", self.LANGCHAIN_PROJECT),
]:
    if value:
        os.environ.setdefault(env_name, value)
```

### 3.2 Metadata propagation

Pass per-request metadata into `astream` so every span in the trace carries identifiers:

```python
# apps/api/app/routers/research.py — existing astream call, extended config
agent.astream(
    {"messages": [{"role": "user", "content": payload.question}]},
    config={
        "configurable": {"thread_id": thread_id},
        "metadata": {
            "request_id": request_id,       # server-generated uuid4
            "prompt_versions": versions_used,
        },
        "tags": [settings.LLM_PROVIDER],
    },
    stream_mode=["values", "messages", "updates"],
)
```

LangGraph propagates this `config` dict to every node and subagent, so all child spans inherit `request_id` and `prompt_versions` automatically.

### 3.3 `.env.example` additions

```env
# LangSmith tracing (optional — omit to disable)
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=ls__...
# LANGCHAIN_PROJECT=chat-agents
```

---

## 4. structlog

### 4.1 `observability/structlog_setup.py`

Called once during `main.py` lifespan startup:

```python
import logging
import structlog

def configure_structlog() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        logger_factory=structlog.PrintLoggerFactory(),
    )
```

`structlog.make_filtering_bound_logger(logging.DEBUG)` is the correct modern API (not the legacy `structlog.BoundLogger`). It respects log-level filtering and is the documented production pattern since structlog 21.2.

### 4.2 `observability/middleware.py`

Starlette middleware that binds a fresh `request_id` before every request:

```python
import structlog
from uuid import uuid4
from starlette.middleware.base import BaseHTTPMiddleware

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=str(uuid4()))
        return await call_next(request)
```

Registered in `main.py`:

```python
app.add_middleware(RequestContextMiddleware)
```

### 4.3 Per-request context binding in the router

After resolving `thread_id` and `versions_used`, bind them into the context:

```python
structlog.contextvars.bind_contextvars(
    thread_id=thread_id,
    prompt_versions=versions_used,
)
```

All subsequent `log.info(...)` / `log.warning(...)` calls automatically include these fields — no need to pass them as keyword arguments.

### 4.4 Logger migration

Replace `logger = logging.getLogger(__name__)` with `log = structlog.get_logger()` in `routers/research.py`. Other modules updated as they are touched; no bulk migration.

### 4.5 Context propagation

`structlog.contextvars` uses Python's `contextvars.ContextVar` internally. Values bound before an `await` are inherited by coroutines and tasks spawned from the same context — including those created with `asyncio.create_task`. This means `request_id` and `thread_id` survive the full async `astream` loop without explicit passing.

---

## 5. Token Budget Guard

### 5.1 New setting

```python
# apps/api/app/config/settings.py
MAX_TOKENS_PER_RUN: int = Field(default=200_000, ge=1000)
```

Added to `.env.example`:

```env
# Token budget per research run (default 200000)
# MAX_TOKENS_PER_RUN=200000
```

### 5.2 Token extraction helper

In LangGraph `messages` stream mode, each iteration yields a **tuple** `(AIMessageChunk, metadata_dict)`. The helper receives only the message (index 0 of the tuple) — never the raw tuple:

```python
from typing import Any

def _extract_token_count(msg: Any) -> int:
    """Read usage_metadata from an AIMessageChunk. Returns 0 if absent."""
    meta = getattr(msg, "usage_metadata", None)
    if not meta:
        return 0
    return meta.get("input_tokens", 0) + meta.get("output_tokens", 0)
```

`usage_metadata` is populated by Anthropic and OpenAI on the final chunk of each message turn. The counter lags by at most one turn — acceptable for a budget guard.

### 5.3 Budget check in the astream loop

```python
cumulative_tokens = 0

async for mode, chunk in agent.astream(...):
    if mode == "messages":
        # chunk is (AIMessageChunk, metadata_dict) in messages mode
        cumulative_tokens += _extract_token_count(chunk[0])
        if cumulative_tokens > settings.MAX_TOKENS_PER_RUN:
            log.warning(
                "token budget exceeded",
                tokens_used=cumulative_tokens,
                limit=settings.MAX_TOKENS_PER_RUN,
            )
            error_reason = "budget_exceeded"
            yield events.budget_exceeded(
                tokens_used=cumulative_tokens,
                limit=settings.MAX_TOKENS_PER_RUN,
            )
            return  # exits generator; finally block emits stream_end(source="error")

    async for ev in mapper.process(mode, chunk):
        if ev["event"] == "text_delta":
            final_report_parts.append(json.loads(ev["data"])["content"])
        yield ev
```

`return` inside an async generator raises `StopAsyncIteration`, cleanly exiting the loop. The existing `finally` block checks `error_reason is not None` and emits `stream_end(final_report_source="error")` — no change needed there.

**Note:** `budget_exceeded` is its own SSE event type. It is **not** routed through the `events.error()` factory and does not set backend `ErrorReason`. The frontend reducer is responsible for setting the appropriate state from the `budget_exceeded` payload directly.

### 5.4 New SSE factory

```python
# apps/api/app/streaming/events.py
def budget_exceeded(tokens_used: int, limit: int) -> dict:
    return _sse(
        "budget_exceeded",
        {
            "tokens_used": tokens_used,
            "limit": limit,
            "message": (
                f"Run stopped: token budget exceeded "
                f"({tokens_used:,} / {limit:,} tokens)."
            ),
        },
    )
```

The backend `ErrorReason = Literal["timeout", "internal", "rate_limited"]` is **not** extended — `budget_exceeded` is a separate event, not an error reason.

---

## 6. SSE Contract Updates

### 6.1 `apps/web/lib/types.ts`

`ErrorReason` is **not** extended — `budget_exceeded` arrives via its own event type, not the `error` event. Add only the new event shape to `SSEEventMap`:

```typescript
// No change to ErrorReason — budget_exceeded is a separate SSE event, not an ErrorReason.

export type SSEEventMap = {
  // ... all existing events unchanged ...
  budget_exceeded: {
    tokens_used: number;
    limit: number;
    message: string;
  };
};
```

> **Pre-existing gap (out of scope):** `memory_updated` is referenced in the architecture doc but absent from both `types.ts` and `events.py`. This spec does not address it — do not add or remove it here.

### 6.2 `apps/web/lib/useResearchStream.ts`

New state field:

```typescript
export type ResearchState = {
  // ... existing fields ...
  budgetExceeded?: { tokens_used: number; limit: number; message: string };
};
```

New reducer case. The `budget_exceeded` event carries its own message, so we populate `state.error` from `data.message` and `state.errorRecoverable = false` — this gives `ErrorView` all the props it needs without requiring an additional `error` SSE event:

```typescript
case "budget_exceeded":
  return {
    ...state,
    status: "error",
    budgetExceeded: data,
    error: data.message,          // populates state.error for ErrorView
    errorRecoverable: false,      // budget exceeded is not auto-recoverable
  };
```

`status: "error"` reuses the existing error path — `StatusBadge` shows "Stopped" without modification. The `budgetExceeded` field is the discriminant `ErrorView` reads to choose amber vs red styling.

The subsequent `stream_end(final_report_source="error")` is handled by the existing reducer case — no change needed.

---

## 7. UI: Inline Error / Warning Display

### 7.1 Remove bottom bar

Delete from `page.tsx`:

```tsx
{state.error && (
  <div className="border-t border-rule bg-[#f6e3df] px-6 py-3 text-sm text-danger">
    <span className="mr-2 font-medium">Something went wrong.</span>
    {state.error}
  </div>
)}
```

### 7.2 Conditional render in main section

```tsx
<section className="min-w-0 flex-1 overflow-y-auto">
  {state.status === "error"
    ? <ErrorView
        error={state.error}
        reason={state.errorReason}
        recoverable={state.errorRecoverable}
        budgetExceeded={state.budgetExceeded}
        onReset={reset}
      />
    : <ReportView text={state.report} status={state.status} source={state.reportSource} />
  }
</section>
```

### 7.3 `ErrorView.tsx` — two visual variants

**Budget exceeded (amber/warning):**

```
┌──────────────────────────────────────────────────┐
│  ⚠  Token budget exceeded                        │
│                                                  │
│  Run stopped at 207,432 / 200,000 tokens.        │
│  The partial report may be incomplete.           │
│                                                  │
│  207,432 ████████████░░  200k limit              │
│                                  [New research]  │
└──────────────────────────────────────────────────┘
```

Colors: `bg-amber/10`, `border-amber/40`, `text-amber`

**Error (red/danger):**

```
┌──────────────────────────────────────────────────┐
│  ✕  Research stopped                             │
│                                                  │
│  The AI provider is temporarily rate-limited.    │
│  Wait 30 seconds and try again.                  │
│                                  [Try again]  ← recoverable only
│                                  [New research]  │
└──────────────────────────────────────────────────┘
```

Colors: `bg-danger/10`, `border-danger/40`, `text-danger`

The progress bar for token usage is a plain `div` with inline width — no library:

```tsx
<div className="h-1.5 w-full rounded-full bg-amber/20">
  <div
    className="h-1.5 rounded-full bg-amber"
    style={{ width: `${Math.min(100, (tokens_used / limit) * 100)}%` }}
  />
</div>
```

---

## 8. Tests

### 8.1 Backend unit (`apps/api/tests/unit/`)

**`test_budget_guard.py`**
- `test_extract_token_count_from_usage_metadata` — helper receives an `AIMessageChunk` directly (not a tuple); returns `input_tokens + output_tokens`
- `test_extract_token_count_missing_metadata` — returns 0 when `usage_metadata` is absent
- `test_budget_exceeded_event_shape` — factory returns dict with correct `event` key and `data` containing `tokens_used`, `limit`, `message`

**`test_structlog_context.py`**
- `test_request_id_bound_in_middleware` — middleware binds `request_id` to contextvars per request
- `test_context_survives_create_task` — value bound with `bind_contextvars` is accessible inside a coroutine launched via `asyncio.create_task` from the same context (plain `await` inherits trivially; this test covers the task boundary)

### 8.2 Backend e2e (`apps/api/tests/e2e/`)

**`test_budget_e2e.py`**
- `test_over_budget_request_yields_budget_exceeded_then_stream_end` — mock agent yields enough `(mode="messages", chunk=(AIMessageChunk_with_usage, {}))` tuples to cross `MAX_TOKENS_PER_RUN`; assert event sequence is `budget_exceeded` → `stream_end(final_report_source="error")`

### 8.3 Frontend (`apps/web/`)

**`useResearchStream.test.ts`**
- `test_budget_exceeded_sets_state` — dispatching `budget_exceeded` frame sets `state.budgetExceeded`, `state.status === "error"`, `state.error === data.message`, `state.errorRecoverable === false`

**`ErrorView.test.tsx`**
- `renders_warning_variant_for_budget_exceeded` — amber classes present, progress bar rendered, no retry button
- `renders_error_variant_with_retry_button` — red classes present, retry button rendered when `recoverable=true`
- `renders_error_variant_without_retry_button` — retry button absent when `recoverable=false`

### 8.4 Out of scope
- LangSmith trace shape — tested upstream by LangChain
- structlog JSON output format — tests the library, not our code

---

## 9. CONTRIBUTING.md Addition

New section: **Enabling tracing locally**

```markdown
## Enabling tracing locally

Add to `apps/api/.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...      # from smith.langchain.com → Settings → API Keys
LANGCHAIN_PROJECT=chat-agents  # project name in LangSmith
```

The app re-exports these to `os.environ` at startup (same pattern as `ANTHROPIC_API_KEY`), so LangChain picks them up automatically. Tracing is disabled by default — omit `LANGCHAIN_TRACING_V2` or set it to `false`.
```

---

## 10. Acceptance Criteria

- [ ] LangSmith shows a trace for every `/research` call, including supervisor + subagent hierarchy
- [ ] All application logs are structured JSON with `thread_id`, `request_id`, `prompt_versions` bound from context
- [ ] Token budget guard aborts runs over `MAX_TOKENS_PER_RUN`; emits `budget_exceeded` SSE event followed by `stream_end(source="error")`
- [ ] `budget_exceeded` renders inline in amber/warning style; `error` renders inline in red style
- [ ] Retry button appears only for `recoverable: true` errors
- [ ] Bottom error bar removed
- [ ] All unit + e2e tests pass; `ruff check . && mypy app/` clean; `tsc` via `next build` clean

---

## 11. Out of Scope

Langfuse, Prometheus, auth, rate limiting, frontend logger / client-side `request_id`, `memory_updated` event gap (pre-existing).
