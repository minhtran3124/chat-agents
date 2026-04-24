# Phase 1: LangSmith Tracing + structlog + Token Budget Guard — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LangSmith tracing, structured JSON logging via structlog, and a token budget guard that aborts oversized `/research` runs — all surfaced in a redesigned inline error/warning UI.

**Architecture:** Three features share observability infra: optional LangSmith env re-export in `Settings`, structlog middleware binding `request_id` / `thread_id` / `prompt_versions` into `contextvars`, and in-stream token accumulation that fires a new `budget_exceeded` SSE event (separate from `error`) when `MAX_TOKENS_PER_RUN` is crossed. The frontend consumes `budget_exceeded` as a distinct variant and a new `ErrorView` component replaces the bottom error bar.

**Tech Stack:** FastAPI 0.115+, `deepagents` / LangGraph 1.0+, `structlog` (new), `sse-starlette`, pydantic-settings, Next.js 14 App Router, React 18, Tailwind 3.4, vitest.

**Source spec:** `docs/superpowers/specs/2026-04-24-phase-1-langsmith-structlog-token-budget-design.md`

**Base branch:** `v1` (NOT `main`). This plan is cut from `v1`, which includes the "Journal" theme UI redesign (`ff3bd59 feat(web): redesign UI as "Journal" theme`) that is not yet on `main`. The spec header's mention of `main` predates that redesign landing on `v1`. Cut the implementation branch from `v1` HEAD so the `ErrorView` component is styled against the Journal UI tokens (`coral`, `amber`, `hairline`, `surface`, `mint`) that exist on `v1` but not `main`.

**PR target:** `v1` (not `main`), until `v1` itself merges down.

---

## File Structure

### Backend (`apps/api/`)

| Action | Path | Responsibility |
| :--- | :--- | :--- |
| Modify | `app/config/settings.py` | Add `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `MAX_TOKENS_PER_RUN`; extend `model_validator` re-export block |
| Modify | `pyproject.toml` | Add `structlog>=24.1` to `dependencies` |
| Modify | `.env.example` | Add commented LangSmith keys + `MAX_TOKENS_PER_RUN` example |
| Create | `app/observability/__init__.py` | Empty package marker |
| Create | `app/observability/structlog_setup.py` | `configure_structlog()` called once at startup |
| Create | `app/observability/middleware.py` | `RequestContextMiddleware` — binds `request_id` per HTTP request |
| Modify | `app/main.py` | Call `configure_structlog()` in lifespan; register `RequestContextMiddleware` |
| Modify | `app/streaming/events.py` | Add `budget_exceeded(tokens_used, limit)` factory |
| Modify | `app/routers/research.py` | Migrate to `structlog.get_logger()`; bind `thread_id`/`prompt_versions` to context; pass `metadata` + `tags` in `astream` config; accumulate tokens via `_extract_token_count`; abort + emit `budget_exceeded` when over limit |
| Create | `tests/unit/test_budget_guard.py` | Unit tests for `_extract_token_count` and `budget_exceeded` factory |
| Create | `tests/unit/test_structlog_context.py` | Unit tests for middleware binding + contextvar task propagation |
| Create | `tests/e2e/test_budget_e2e.py` | Full-stream e2e: mocked agent crosses budget → `budget_exceeded` → `stream_end(error)` |
| Modify | `tests/unit/test_settings.py` | Add tests for `MAX_TOKENS_PER_RUN` default / bounds + LangChain re-export behavior |
| Modify | `tests/unit/test_events.py` | Add test for `budget_exceeded` factory shape |

### Frontend (`apps/web/`)

| Action | Path | Responsibility |
| :--- | :--- | :--- |
| Modify | `lib/types.ts` | Add `budget_exceeded` entry to `SSEEventMap` |
| Modify | `lib/useResearchStream.ts` | Add `budgetExceeded` state field + reducer case |
| Modify | `lib/useResearchStream.test.ts` | Add test for `budget_exceeded` dispatch |
| Create | `app/research/components/ErrorView.tsx` | Two-variant inline error/warning panel |
| Create | `app/research/components/ErrorView.test.tsx` | Tests for warning + error variants |
| Modify | `app/research/page.tsx` | Remove bottom bar; conditionally render `ErrorView` in main section |

### Docs

| Action | Path | Responsibility |
| :--- | :--- | :--- |
| Modify | `CONTRIBUTING.md` | New "Enabling tracing locally" section |

---

## Decomposition Notes

The plan is broken into **seven logically independent chunks**. Each chunk is independently testable and commits on green. Chunks 1–4 are backend; chunks 5–6 are frontend; chunk 7 is docs + final verification.

- **Chunk 1** — Settings + dependency + `.env.example` (LangSmith activation infrastructure)
- **Chunk 2** — `observability` package + `main.py` wiring
- **Chunk 3** — Router: structlog migration + LangSmith metadata propagation (no behavior change beyond logging)
- **Chunk 4** — Token budget guard: SSE factory + router-side accumulation + abort
- **Chunk 5** — Frontend types + `useResearchStream` reducer
- **Chunk 6** — `ErrorView` component + `page.tsx` integration
- **Chunk 7** — `CONTRIBUTING.md` update + full cross-cutting verification

**Commit cadence:** one commit per task (not per step). Each task's final step is an explicit `git commit`.

---

## Chunk 1: Backend Settings + Dependency + .env.example

`★ Insight ─────────────────────────────────────`
The existing `Settings` class already re-exports provider keys to `os.environ` via `model_validator` because `pydantic-settings` reads `.env` into the model but **does not** mutate the process environment. LangChain only picks up tracing when `LANGCHAIN_TRACING_V2` is a real env var — so we reuse the exact same pattern. Three optional fields keep tracing opt-in: omit them and nothing changes.
`─────────────────────────────────────────────────`

### Task 1.1: Add `structlog` dependency

**Files:**
- Modify: `apps/api/pyproject.toml` (dependencies list)

- [ ] **Step 1: Add `structlog` to the dependencies array**

Open `apps/api/pyproject.toml`. In the `[project].dependencies` list, add:

```toml
"structlog>=24.1",
```

Place it in alphabetical position (after `sse-starlette`, before `tavily-python`).

- [ ] **Step 2: Install the dependency**

Run from `apps/api/`:

```bash
pip install -e ".[dev]"
```

Expected: `Successfully installed structlog-...`

- [ ] **Step 3: Verify import**

Run:

```bash
python -c "import structlog; print(structlog.__version__)"
```

Expected: a version string ≥ 24.1.

- [ ] **Step 4: Commit**

```bash
git add apps/api/pyproject.toml
git commit -m "chore(api): add structlog dependency for Phase 1 observability"
```

### Task 1.2: Extend `Settings` with LangSmith + `MAX_TOKENS_PER_RUN`

**Files:**
- Modify: `apps/api/app/config/settings.py`
- Test: `apps/api/tests/unit/test_settings.py`

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/unit/test_settings.py`:

```python
@pytest.mark.unit
def test_max_tokens_per_run_default_is_200000(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import Settings

    s = Settings(_env_file=None)
    assert s.MAX_TOKENS_PER_RUN == 200_000


@pytest.mark.unit
def test_max_tokens_per_run_rejects_below_minimum(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import Settings

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, MAX_TOKENS_PER_RUN=100)
    assert "MAX_TOKENS_PER_RUN" in str(exc.value)


@pytest.mark.unit
def test_langchain_tracing_env_exported_when_set(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)

    from app.config.settings import Settings

    Settings(
        _env_file=None,
        LANGCHAIN_TRACING_V2="true",
        LANGCHAIN_API_KEY="ls__test",
        LANGCHAIN_PROJECT="chat-agents",
    )
    import os

    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    assert os.environ.get("LANGCHAIN_API_KEY") == "ls__test"
    assert os.environ.get("LANGCHAIN_PROJECT") == "chat-agents"


@pytest.mark.unit
def test_langchain_env_not_exported_when_unset(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    from app.config.settings import Settings

    Settings(_env_file=None)
    import os

    assert "LANGCHAIN_TRACING_V2" not in os.environ
    assert "LANGCHAIN_API_KEY" not in os.environ
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `apps/api/`:

```bash
pytest tests/unit/test_settings.py -v -k "max_tokens or langchain"
```

Expected: 4 tests FAIL — `MAX_TOKENS_PER_RUN` / `LANGCHAIN_*` not defined on `Settings`.

- [ ] **Step 3: Extend `Settings`**

Edit `apps/api/app/config/settings.py`:

After the existing `RESEARCH_TIMEOUT_S` field and before `LOG_LEVEL`, add:

```python
    MAX_TOKENS_PER_RUN: int = Field(
        default=200_000,
        ge=1_000,
        description="Token budget per /research run. Over this, the run is aborted.",
    )

    LANGCHAIN_TRACING_V2: str | None = None
    LANGCHAIN_API_KEY: str | None = None
    LANGCHAIN_PROJECT: str | None = None
```

Then extend the `_resolve_and_validate` method's re-export block. After the existing `_env_keys` loop and the `TAVILY_API_KEY` block, add:

```python
        for env_name, value in (
            ("LANGCHAIN_TRACING_V2", self.LANGCHAIN_TRACING_V2),
            ("LANGCHAIN_API_KEY", self.LANGCHAIN_API_KEY),
            ("LANGCHAIN_PROJECT", self.LANGCHAIN_PROJECT),
        ):
            if value:
                os.environ.setdefault(env_name, value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/unit/test_settings.py -v
```

Expected: all settings tests PASS (old + 4 new).

- [ ] **Step 5: Run linters**

Run:

```bash
ruff check app/config/settings.py tests/unit/test_settings.py
ruff format --check app/config/settings.py tests/unit/test_settings.py
mypy app/config/settings.py
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/config/settings.py apps/api/tests/unit/test_settings.py
git commit -m "feat(api): add MAX_TOKENS_PER_RUN + LangSmith env re-export"
```

### Task 1.3: Update `.env.example`

**Files:**
- Modify: `apps/api/.env.example`

- [ ] **Step 1: Append new sections**

At the end of `apps/api/.env.example`, add:

```env

# Token budget per research run (default 200000)
# MAX_TOKENS_PER_RUN=200000

# LangSmith tracing (optional — omit to disable)
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=ls__...
# LANGCHAIN_PROJECT=chat-agents
```

- [ ] **Step 2: Verify the example file is syntactically valid**

No automated check — visually confirm the new block matches the style of existing commented-out lines.

- [ ] **Step 3: Commit**

```bash
git add apps/api/.env.example
git commit -m "docs(api): document MAX_TOKENS_PER_RUN + LangSmith env in .env.example"
```

---

**Chunk 1 review gate:** Before moving to Chunk 2, verify:
- [ ] `pytest tests/unit/test_settings.py` green
- [ ] `ruff check . && mypy app/` green
- [ ] Three new commits on the branch

---

## Chunk 2: Observability Package + main.py Wiring

`★ Insight ─────────────────────────────────────`
`structlog.contextvars` uses Python's `contextvars.ContextVar` — values bound before an `await` propagate across awaits and into coroutines spawned by `asyncio.create_task` from the same context. That's what lets us bind `request_id` once in middleware and have every downstream log line include it automatically, even through the async `astream` loop. The structlog docs recommend `structlog.make_filtering_bound_logger(logging.DEBUG)` as the modern replacement for the deprecated `structlog.BoundLogger` — it respects log-level filtering and is the documented production pattern since structlog 21.2.
`─────────────────────────────────────────────────`

### Task 2.1: Create the `observability` package

**Files:**
- Create: `apps/api/app/observability/__init__.py`
- Create: `apps/api/app/observability/structlog_setup.py`

- [ ] **Step 1: Create the package marker**

Create `apps/api/app/observability/__init__.py`:

```python
"""Observability: structlog configuration and request-context middleware."""
```

- [ ] **Step 2: Create `structlog_setup.py`**

Create `apps/api/app/observability/structlog_setup.py`:

```python
import logging

import structlog


def configure_structlog() -> None:
    """Configure structlog for JSON output with contextvar merging.

    Called once from the FastAPI lifespan. Processors, in order:
      - merge contextvars (request_id, thread_id, prompt_versions)
      - add log level
      - ISO timestamp
      - JSON render
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

> **Note on log level:** The spec example uses `logging.DEBUG`, but our `Settings.LOG_LEVEL` defaults to `"INFO"`. We hard-code INFO here to match existing behavior and avoid debug-level noise in production by default. If the team later wants DEBUG in dev, read `settings.LOG_LEVEL` inside `configure_structlog`.

- [ ] **Step 3: Verify import**

Run from `apps/api/`:

```bash
python -c "from app.observability.structlog_setup import configure_structlog; configure_structlog(); import structlog; structlog.get_logger().info('ok')"
```

Expected: a single-line JSON log with `event="ok"`, `level="info"`, and a timestamp.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/observability/__init__.py apps/api/app/observability/structlog_setup.py
git commit -m "feat(api): add structlog configuration module"
```

### Task 2.2: Create `RequestContextMiddleware`

**Files:**
- Create: `apps/api/app/observability/middleware.py`
- Test: `apps/api/tests/unit/test_structlog_context.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/unit/test_structlog_context.py`:

```python
import asyncio

import pytest
import structlog
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.observability.middleware import RequestContextMiddleware


@pytest.mark.unit
def test_request_id_bound_in_middleware():
    captured: dict[str, str] = {}

    async def endpoint(request: Request) -> JSONResponse:
        ctx = structlog.contextvars.get_contextvars()
        captured["request_id"] = ctx.get("request_id", "")
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/test", endpoint)])
    app.add_middleware(RequestContextMiddleware)

    client = TestClient(app)
    res1 = client.get("/test")
    assert res1.status_code == 200
    rid1 = captured["request_id"]
    assert len(rid1) == 36  # uuid4 str length

    res2 = client.get("/test")
    assert res2.status_code == 200
    rid2 = captured["request_id"]
    assert len(rid2) == 36
    assert rid1 != rid2  # fresh per request


@pytest.mark.unit
async def test_context_survives_create_task():
    """Values bound before create_task are visible inside the task."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="parent-req")

    captured: dict[str, str] = {}

    async def child() -> None:
        ctx = structlog.contextvars.get_contextvars()
        captured["request_id"] = ctx.get("request_id", "")

    await asyncio.create_task(child())
    assert captured["request_id"] == "parent-req"

    structlog.contextvars.clear_contextvars()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/test_structlog_context.py -v
```

Expected: import error — `RequestContextMiddleware` does not exist.

- [ ] **Step 3: Create the middleware**

Create `apps/api/app/observability/middleware.py`:

```python
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a fresh `request_id` to structlog contextvars on every request.

    Values bound here propagate through `await` chains and into tasks
    spawned from the same context (structlog.contextvars -> ContextVar).
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next
    ) -> Response:
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=str(uuid4()))
        return await call_next(request)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/unit/test_structlog_context.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Run linters**

```bash
ruff check app/observability/ tests/unit/test_structlog_context.py
ruff format --check app/observability/ tests/unit/test_structlog_context.py
mypy app/observability/
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/observability/middleware.py apps/api/tests/unit/test_structlog_context.py
git commit -m "feat(api): add RequestContextMiddleware for structlog request_id"
```

### Task 2.3: Wire structlog + middleware into `main.py`

**Files:**
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Register middleware + call `configure_structlog`**

Edit `apps/api/app/main.py`.

Add to imports (top of file):

```python
from app.observability.middleware import RequestContextMiddleware
from app.observability.structlog_setup import configure_structlog
```

In the `lifespan` coroutine, **before** `registry.reload()`, call:

```python
    configure_structlog()
```

After the `CORSMiddleware` registration block, add:

```python
app.add_middleware(RequestContextMiddleware)
```

> **Middleware order note:** Starlette applies middleware in reverse-add order (LIFO). `RequestContextMiddleware` added after `CORSMiddleware` means CORS runs first on the way in — fine, because CORS's preflight `OPTIONS` handler short-circuits before our middleware. For all non-preflight requests, both run.

- [ ] **Step 2: Start the server and hit a route**

Run in one terminal from `apps/api/`:

```bash
uvicorn app.main:app --port 8001
```

In another terminal:

```bash
curl -s http://localhost:8001/health
```

Expected: `{"status":"ok"}`. Server stdout shows a JSON log line (uvicorn's own lines remain unstructured — that's fine; only structlog calls are JSON).

Stop the server.

- [ ] **Step 3: Run e2e to confirm no regression**

Run:

```bash
pytest tests/e2e/ -v
```

Expected: all existing e2e tests still pass.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/main.py
git commit -m "feat(api): wire structlog + RequestContextMiddleware into app lifespan"
```

---

**Chunk 2 review gate:**
- [ ] `pytest tests/unit/test_structlog_context.py tests/e2e/` green
- [ ] Manual `/health` returns JSON log line
- [ ] Three new commits

---

## Chunk 3: Router — structlog Migration + LangSmith Metadata

`★ Insight ─────────────────────────────────────`
Keep the logger migration *surgical*: only replace calls inside `routers/research.py`. Other modules (`agent_factory`, `llm_factory`, etc.) still use stdlib `logging` and don't need to change — structlog's JSON renderer only touches calls made through `structlog.get_logger()`. Mixed logger types in the same process is fine. The `metadata` we inject into the `astream` `config` dict is propagated by LangGraph to every span in the LangSmith trace — no additional per-subagent wiring needed.
`─────────────────────────────────────────────────`

### Task 3.1: Swap stdlib logger for structlog in the research router

**Files:**
- Modify: `apps/api/app/routers/research.py`
- Test: `apps/api/tests/unit/test_research_router.py` (only if structlog migration breaks existing assertions — otherwise no change)

- [ ] **Step 1: Replace the logger and call sites**

Edit `apps/api/app/routers/research.py`:

Replace:

```python
import logging
...
logger = logging.getLogger(__name__)
```

with:

```python
import structlog
...
log = structlog.get_logger(__name__)
```

Remove the `logging` import if no longer used.

Convert each `logger.<level>(fmt, *args)` call to structlog's keyword-argument form. Concrete replacements:

**Before:**
```python
logger.info(
    "[RESEARCH] Agent invoked thread_id=%s prompt_versions=%s question=%r",
    thread_id,
    versions_used,
    payload.question[:120],
)
```

**After:**
```python
log.info(
    "research.invoked",
    question_preview=payload.question[:120],
)
```

(`thread_id` and `prompt_versions` will come from contextvars once Task 3.2 binds them — don't pass them explicitly here.)

**Before:**
```python
logger.warning(
    "[RESEARCH] Timeout after %ds thread_id=%s",
    settings.RESEARCH_TIMEOUT_S,
    thread_id,
)
```

**After:**
```python
log.warning(
    "research.timeout",
    timeout_s=settings.RESEARCH_TIMEOUT_S,
)
```

**Before:**
```python
logger.warning(
    "[RESEARCH] Rate limit hit thread_id=%s: %s",
    thread_id,
    exc,
)
```

**After:**
```python
log.warning("research.rate_limited", error=str(exc))
```

**Before:**
```python
logger.error(
    "[RESEARCH] Stream error — agent run abandoned:\n%s",
    traceback.format_exc(),
)
```

**After:**
```python
log.exception("research.internal_error")
```

(structlog's `.exception` captures the active traceback automatically — you can drop the `traceback` import if it's no longer referenced elsewhere.)

**Before:**
```python
logger.warning(
    "[RESEARCH] Final-report fallback triggered — streamed only %d "
    "chars; using %s (%d chars). Prompt compliance issue worth "
    "investigating (main prompt version=%s).",
    len(streamed_report),
    FALLBACK_DRAFT_FILENAME,
    len(draft),
    versions_used.get("main"),
)
```

**After:**
```python
log.warning(
    "research.fallback_to_draft",
    streamed_chars=len(streamed_report),
    draft_filename=FALLBACK_DRAFT_FILENAME,
    draft_chars=len(draft),
    main_prompt_version=versions_used.get("main"),
)
```

**Before:**
```python
logger.info(
    "[RESEARCH] Stream complete thread_id=%s report_chars=%d source=%s "
    "nodes_seen=%s prompt_versions=%s usage=%s",
    thread_id,
    len(final_report),
    final_report_source,
    sorted(mapper.seen_nodes),
    versions_used,
    usage,
)
```

**After:**
```python
log.info(
    "research.stream_complete",
    report_chars=len(final_report),
    final_report_source=final_report_source,
    nodes_seen=sorted(mapper.seen_nodes),
    usage=usage,
)
```

- [ ] **Step 2: Run unit + e2e tests**

Run:

```bash
pytest tests/ -v
```

Expected: everything still passes (logs change, behavior doesn't). If a test was asserting on stdout log text — update it to match the new structlog message, or replace it with a behavior-level assertion.

- [ ] **Step 3: Run linters**

```bash
ruff check app/routers/research.py
ruff format --check app/routers/research.py
mypy app/routers/research.py
```

Expected: clean. If `logging` or `traceback` imports are now unused, `ruff --fix` will remove them.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/routers/research.py
git commit -m "refactor(api): migrate research router logger to structlog"
```

### Task 3.2: Bind `thread_id` + `prompt_versions` into contextvars and pass LangSmith metadata

**Files:**
- Modify: `apps/api/app/routers/research.py`

- [ ] **Step 1: Bind context at the top of the handler**

Edit `apps/api/app/routers/research.py`.

Immediately after `thread_id = payload.thread_id or "default-user"` (and before the `try:` that builds the agent), add:

```python
    structlog.contextvars.bind_contextvars(
        thread_id=thread_id,
        prompt_versions=versions_used,
    )
```

- [ ] **Step 2: Capture `request_id` from contextvars for the agent call**

Inside the `generator` coroutine, near the top (before `yield events.stream_start(thread_id)`), read the current `request_id`:

```python
        request_id = structlog.contextvars.get_contextvars().get("request_id", "")
```

- [ ] **Step 3: Extend the `astream` config with metadata + tags**

In the same generator, replace:

```python
                async for mode, chunk in agent.astream(
                    {"messages": [{"role": "user", "content": payload.question}]},
                    config={"configurable": {"thread_id": thread_id}},
                    stream_mode=["values", "messages", "updates"],
                ):
```

with:

```python
                async for mode, chunk in agent.astream(
                    {"messages": [{"role": "user", "content": payload.question}]},
                    config={
                        "configurable": {"thread_id": thread_id},
                        "metadata": {
                            "request_id": request_id,
                            "prompt_versions": versions_used,
                        },
                        "tags": [settings.LLM_PROVIDER],
                    },
                    stream_mode=["values", "messages", "updates"],
                ):
```

- [ ] **Step 4: Run existing router + e2e tests**

Run:

```bash
pytest tests/unit/test_research_router.py tests/e2e/ -v
```

Expected: all pass. Existing tests that patch `build_research_agent` with a mock will receive the new `config` dict — they don't assert on its shape, so they continue to pass.

- [ ] **Step 5: Run linters**

```bash
ruff check app/routers/research.py && mypy app/routers/research.py
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/routers/research.py
git commit -m "feat(api): bind structlog context + propagate LangSmith metadata"
```

---

**Chunk 3 review gate:**
- [ ] Full backend test suite green (`pytest`)
- [ ] Starting the server and hitting `/research` in manual smoke still streams events end-to-end
- [ ] Two new commits

---

## Chunk 4: Token Budget Guard (Backend)

`★ Insight ─────────────────────────────────────`
LangGraph's `messages` stream mode yields a **tuple** `(AIMessageChunk, metadata_dict)` — the helper must receive only index 0 of that tuple. `usage_metadata` lands on the *final* chunk of each message turn (not every chunk), so the counter lags by up to one turn. That's acceptable for a budget guard — worst case we stop one turn late. We abort the async generator with `return`, which raises `StopAsyncIteration` cleanly; the existing `finally` block sees `error_reason is not None` and emits `stream_end(final_report_source="error")` automatically. The `ErrorReason` literal stays `timeout | internal | rate_limited`; we use a broader *local* type so `error_reason` can also hold our budget sentinel without breaking the `events.error()` factory signature.
`─────────────────────────────────────────────────`

### Task 4.1: Add `budget_exceeded` SSE factory

**Files:**
- Modify: `apps/api/app/streaming/events.py`
- Test: `apps/api/tests/unit/test_events.py`

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/unit/test_events.py`:

```python
@pytest.mark.unit
def test_budget_exceeded_factory_shape():
    from app.streaming.events import budget_exceeded

    ev = budget_exceeded(tokens_used=207_432, limit=200_000)
    assert ev["event"] == "budget_exceeded"
    data = json.loads(ev["data"])
    assert data["tokens_used"] == 207_432
    assert data["limit"] == 200_000
    assert "207,432" in data["message"]
    assert "200,000" in data["message"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/unit/test_events.py::test_budget_exceeded_factory_shape -v
```

Expected: FAIL — `budget_exceeded` is not importable.

- [ ] **Step 3: Add the factory**

Append to `apps/api/app/streaming/events.py`:

```python
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

> **Contract note:** `budget_exceeded` is its own event type — it is NOT an `ErrorReason`. Do NOT add `"budget_exceeded"` to the `ErrorReason` literal in this file. The existing `ErrorReason` stays `timeout | internal | rate_limited`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/unit/test_events.py -v
```

Expected: all event tests PASS (old + new).

- [ ] **Step 5: Run linters**

```bash
ruff check app/streaming/events.py && mypy app/streaming/events.py
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/streaming/events.py apps/api/tests/unit/test_events.py
git commit -m "feat(api): add budget_exceeded SSE event factory"
```

### Task 4.2: Add `_extract_token_count` helper + unit tests

**Files:**
- Create: `apps/api/tests/unit/test_budget_guard.py`
- Modify: `apps/api/app/routers/research.py` (add helper function)

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/unit/test_budget_guard.py`:

```python
from types import SimpleNamespace

import pytest


@pytest.mark.unit
def test_extract_token_count_from_usage_metadata():
    from app.routers.research import _extract_token_count

    msg = SimpleNamespace(usage_metadata={"input_tokens": 100, "output_tokens": 50})
    assert _extract_token_count(msg) == 150


@pytest.mark.unit
def test_extract_token_count_missing_metadata():
    from app.routers.research import _extract_token_count

    msg = SimpleNamespace()  # no usage_metadata attribute
    assert _extract_token_count(msg) == 0


@pytest.mark.unit
def test_extract_token_count_metadata_none():
    from app.routers.research import _extract_token_count

    msg = SimpleNamespace(usage_metadata=None)
    assert _extract_token_count(msg) == 0


@pytest.mark.unit
def test_extract_token_count_partial_metadata():
    """Only input_tokens set — output_tokens defaults to 0."""
    from app.routers.research import _extract_token_count

    msg = SimpleNamespace(usage_metadata={"input_tokens": 42})
    assert _extract_token_count(msg) == 42
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/test_budget_guard.py -v
```

Expected: import error — `_extract_token_count` does not exist.

- [ ] **Step 3: Add the helper**

Edit `apps/api/app/routers/research.py`. Near the top of the module (after the existing `MIN_STREAM_REPORT_CHARS` / `FALLBACK_DRAFT_FILENAME` constants, before `router = APIRouter(...)`), add:

```python
from typing import Any


def _extract_token_count(msg: Any) -> int:
    """Read usage_metadata from an AIMessageChunk. Returns 0 if absent.

    LangChain populates usage_metadata on the final chunk of each message
    turn — the counter lags by at most one turn, acceptable for a budget
    guard that only needs to catch overruns.
    """
    meta = getattr(msg, "usage_metadata", None)
    if not meta:
        return 0
    return meta.get("input_tokens", 0) + meta.get("output_tokens", 0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/unit/test_budget_guard.py -v
```

Expected: all four tests PASS.

- [ ] **Step 5: Run linters**

```bash
ruff check app/routers/research.py tests/unit/test_budget_guard.py
mypy app/routers/research.py
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/routers/research.py apps/api/tests/unit/test_budget_guard.py
git commit -m "feat(api): add _extract_token_count helper for budget guard"
```

### Task 4.3: Wire the budget guard into the `astream` loop

**Files:**
- Modify: `apps/api/app/routers/research.py`

- [ ] **Step 1: Widen the local `error_reason` type**

In `apps/api/app/routers/research.py`, inside the `generator()` function, change:

```python
        error_reason: ErrorReason | None = None
```

to:

```python
        # Local type is wider than ErrorReason because the budget sentinel
        # "budget_exceeded" drives the error `finally` path but is NOT a
        # valid argument to events.error().
        error_reason: str | None = None
```

Also remove the `ErrorReason` import if no longer referenced elsewhere in the file (it's not — `events.error("timeout")` uses a literal string at the call site).

- [ ] **Step 2: Add token accumulator + budget check inside the stream loop**

Inside the `try:` block, before the `async for mode, chunk in agent.astream(...)` loop, initialize a counter:

```python
                cumulative_tokens = 0
```

Inside the `async for mode, chunk in agent.astream(...)` loop, **before** the existing `async for ev in mapper.process(mode, chunk):` line, insert:

```python
                    if mode == "messages":
                        # chunk is (AIMessageChunk, metadata_dict) in messages mode
                        cumulative_tokens += _extract_token_count(chunk[0])
                        if cumulative_tokens > settings.MAX_TOKENS_PER_RUN:
                            log.warning(
                                "research.budget_exceeded",
                                tokens_used=cumulative_tokens,
                                limit=settings.MAX_TOKENS_PER_RUN,
                            )
                            error_reason = "budget_exceeded"
                            yield events.budget_exceeded(
                                tokens_used=cumulative_tokens,
                                limit=settings.MAX_TOKENS_PER_RUN,
                            )
                            return
```

> **Why `return` works:** `return` inside an async generator raises `StopAsyncIteration`, which cleanly exits the `async for`. The surrounding `try/finally` runs — the `finally` block already emits `stream_end(final_report_source="error")` whenever `error_reason is not None`.

- [ ] **Step 3: Type check**

Run:

```bash
mypy app/routers/research.py
```

Expected: clean. If mypy complains about `"budget_exceeded"` not being a valid `ErrorReason`, double-check that Step 1 widened the annotation to `str | None`.

- [ ] **Step 4: Commit (before e2e — e2e lives in Task 4.4)**

```bash
git add apps/api/app/routers/research.py
git commit -m "feat(api): abort runs exceeding MAX_TOKENS_PER_RUN with budget_exceeded event"
```

### Task 4.4: E2E test for the budget path

**Files:**
- Create: `apps/api/tests/e2e/test_budget_e2e.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/e2e/test_budget_e2e.py`:

```python
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_over_budget_request_yields_budget_exceeded_then_stream_end(monkeypatch):
    """Mocked agent crosses MAX_TOKENS_PER_RUN — expect budget_exceeded → stream_end(error)."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    import app.config.settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "MAX_TOKENS_PER_RUN", 1_000)

    async def fake_astream(*args, **kwargs):
        # Each messages chunk reports 600 tokens — two chunks crosses 1000.
        msg1 = SimpleNamespace(usage_metadata={"input_tokens": 400, "output_tokens": 200})
        yield ("messages", (msg1, {}))
        msg2 = SimpleNamespace(usage_metadata={"input_tokens": 400, "output_tokens": 200})
        yield ("messages", (msg2, {}))
        # This chunk should never be processed — generator should have returned.
        yield ("values", {"messages": [], "files": {}})

    fake_agent = MagicMock()
    fake_agent.astream = fake_astream
    fake_agent.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    events_seen: list[tuple[str, dict]] = []
    with patch("app.routers.research.build_research_agent", return_value=fake_agent):
        from app.main import app

        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
            client.stream("POST", "/research", json={"question": "anything"}) as resp,
        ):
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    events_seen.append((line[len("event: "):].strip(), {}))
                elif line.startswith("data: ") and events_seen:
                    events_seen[-1] = (
                        events_seen[-1][0],
                        json.loads(line[len("data: "):]),
                    )

    names = [name for name, _ in events_seen]
    assert names[0] == "stream_start"
    assert "budget_exceeded" in names
    assert names[-1] == "stream_end"

    budget_data = next(d for n, d in events_seen if n == "budget_exceeded")
    assert budget_data["limit"] == 1_000
    assert budget_data["tokens_used"] >= 1_000

    end_data = events_seen[-1][1]
    assert end_data["final_report_source"] == "error"
```

- [ ] **Step 2: Run the test**

Run:

```bash
pytest tests/e2e/test_budget_e2e.py -v
```

Expected: PASS.

- [ ] **Step 3: Run the full suite**

Run:

```bash
pytest tests/ -v
```

Expected: everything green.

- [ ] **Step 4: Run linters + type-check**

```bash
ruff check . && ruff format --check . && mypy app/
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add apps/api/tests/e2e/test_budget_e2e.py
git commit -m "test(api): e2e coverage for budget_exceeded → stream_end(error) path"
```

---

**Chunk 4 review gate:**
- [ ] Full backend test suite green
- [ ] Four new commits
- [ ] Manual smoke: run `/research` with `MAX_TOKENS_PER_RUN=1000` against a real question — verify `budget_exceeded` event appears in `curl -N` output before `stream_end`

---

## Chunk 5: Frontend Types + Reducer

`★ Insight ─────────────────────────────────────`
The reducer's `budget_exceeded` case populates `state.error` from the event's `message` field, so `ErrorView` can read either `state.error` (text) *or* `state.budgetExceeded` (structured). The dual write is intentional: `state.budgetExceeded` is the discriminant `ErrorView` uses to pick warning-vs-error styling, while `state.error` ensures any consumer that still keys on the generic error text (like a future analytics hook) keeps working. `errorRecoverable: false` hides the retry button — budget overruns are never "just retry."
`─────────────────────────────────────────────────`

### Task 5.1: Add `budget_exceeded` to `SSEEventMap`

**Files:**
- Modify: `apps/web/lib/types.ts`

- [ ] **Step 1: Extend `SSEEventMap`**

Edit `apps/web/lib/types.ts`. Inside the `SSEEventMap` type, after the `error` entry and before `stream_end`, add:

```typescript
  budget_exceeded: { tokens_used: number; limit: number; message: string };
```

> **Do NOT** add `"budget_exceeded"` to the `ErrorReason` union — the backend keeps `ErrorReason = "timeout" | "internal" | "rate_limited"` and `budget_exceeded` is a separate event.

- [ ] **Step 2: Verify type-check**

Run from `apps/web/`:

```bash
npm run lint
npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add apps/web/lib/types.ts
git commit -m "feat(web): add budget_exceeded to SSEEventMap"
```

### Task 5.2: Add `budgetExceeded` state + reducer case

**Files:**
- Modify: `apps/web/lib/useResearchStream.ts`
- Test: `apps/web/lib/useResearchStream.test.ts`

- [ ] **Step 1: Write the failing tests**

Append to `apps/web/lib/useResearchStream.test.ts`:

```typescript
describe("useResearchStream reducer — budget_exceeded event", () => {
  it("sets budgetExceeded, status:'error', error, and errorRecoverable:false", () => {
    const frame: SSEFrame = {
      event: "budget_exceeded",
      data: {
        tokens_used: 207_432,
        limit: 200_000,
        message: "Run stopped: token budget exceeded (207,432 / 200,000 tokens).",
      },
    };
    const next = reducer(initial, frame);
    expect(next.status).toBe("error");
    expect(next.error).toBe(
      "Run stopped: token budget exceeded (207,432 / 200,000 tokens).",
    );
    expect(next.errorRecoverable).toBe(false);
    expect(next.budgetExceeded).toEqual({
      tokens_used: 207_432,
      limit: 200_000,
      message: "Run stopped: token budget exceeded (207,432 / 200,000 tokens).",
    });
  });

  it("stream_end after budget_exceeded preserves error state and reports source='error'", () => {
    const afterBudget = reducer(initial, {
      event: "budget_exceeded",
      data: {
        tokens_used: 250_000,
        limit: 200_000,
        message: "boom",
      },
    } as SSEFrame);

    const afterEnd = reducer(afterBudget, {
      event: "stream_end",
      data: {
        final_report: "",
        usage: {},
        versions_used: {},
        final_report_source: "error",
      },
    } as SSEFrame);

    expect(afterEnd.status).toBe("error");
    expect(afterEnd.reportSource).toBe("error");
    expect(afterEnd.budgetExceeded).toEqual(afterBudget.budgetExceeded);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
npm test -- useResearchStream
```

Expected: two new tests FAIL (type error + unknown event no-op behavior).

- [ ] **Step 3: Add `budgetExceeded` to state shape**

Edit `apps/web/lib/useResearchStream.ts`.

In the `ResearchState` type, after `errorRecoverable?: boolean;`, add:

```typescript
  budgetExceeded?: { tokens_used: number; limit: number; message: string };
```

- [ ] **Step 4: Add the reducer case**

Still in `useResearchStream.ts`, inside the `reducer` function's `switch (frame.event)`, add a new case after `"error"` and before `"stream_end"`:

```typescript
    case "budget_exceeded":
      return {
        ...state,
        status: "error",
        budgetExceeded: data,
        error: data.message,
        errorRecoverable: false,
      };
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
npm test -- useResearchStream
```

Expected: all reducer tests PASS.

- [ ] **Step 6: Run lint + type-check**

```bash
npm run lint
npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add apps/web/lib/useResearchStream.ts apps/web/lib/useResearchStream.test.ts
git commit -m "feat(web): handle budget_exceeded event in research reducer"
```

---

**Chunk 5 review gate:**
- [ ] `npm test` green
- [ ] `npm run lint` + `tsc --noEmit` clean
- [ ] Two new commits

---

## Chunk 6: ErrorView Component + page.tsx Integration

`★ Insight ─────────────────────────────────────`
The project's Tailwind config defines `amber` and `coral` (not `warning`/`danger` as the spec hints). `StatusBadge` already uses `text-coral` / `border-coral/30` for the error state — we match that for the red error variant. The progress bar is a plain nested `<div>` with inline `style={{ width: ... }}` — don't reach for a chart library. Capping `Math.min(100, ...)` keeps the bar from overflowing when `tokens_used` exceeds `limit` (which will always be true when this renders).
`─────────────────────────────────────────────────`

### Task 6.1: Create `ErrorView` component

**Files:**
- Create: `apps/web/app/research/components/ErrorView.tsx`
- Test: `apps/web/app/research/components/ErrorView.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `apps/web/app/research/components/ErrorView.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ErrorView } from "./ErrorView";

describe("ErrorView", () => {
  it("renders warning (amber) variant for budget_exceeded", () => {
    const { container } = render(
      <ErrorView
        budgetExceeded={{
          tokens_used: 207_432,
          limit: 200_000,
          message: "Run stopped: token budget exceeded (207,432 / 200,000 tokens).",
        }}
        onReset={vi.fn()}
      />,
    );

    expect(screen.getByText(/token budget exceeded/i)).toBeTruthy();
    expect(screen.getByText(/207,432/)).toBeTruthy();
    // Progress bar present
    expect(container.querySelector("[data-testid='budget-progress']")).not.toBeNull();
    // No retry button for budget
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
    // New-research button always present
    expect(screen.getByRole("button", { name: /new research/i })).toBeTruthy();
    // Amber variant styling
    expect(container.querySelector(".border-amber\\/40")).not.toBeNull();
  });

  it("renders error (coral) variant with retry button when recoverable", () => {
    const onReset = vi.fn();
    render(
      <ErrorView
        error="Research timed out."
        reason="timeout"
        recoverable={true}
        onReset={onReset}
      />,
    );
    expect(screen.getByText(/research timed out/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /try again/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /new research/i })).toBeTruthy();
  });

  it("renders error variant without retry button when not recoverable", () => {
    render(
      <ErrorView
        error="Something failed."
        reason="internal"
        recoverable={false}
        onReset={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
    expect(screen.getByRole("button", { name: /new research/i })).toBeTruthy();
  });

  it("new-research button invokes onReset", async () => {
    const onReset = vi.fn();
    const { getByRole } = render(
      <ErrorView error="x" reason="internal" recoverable={false} onReset={onReset} />,
    );
    (getByRole("button", { name: /new research/i }) as HTMLButtonElement).click();
    expect(onReset).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `apps/web/`:

```bash
npm test -- ErrorView
```

Expected: FAIL — `ErrorView` does not exist.

- [ ] **Step 3: Create the component**

Create `apps/web/app/research/components/ErrorView.tsx`:

```tsx
import type { ErrorReason } from "@/lib/types";

type BudgetExceeded = { tokens_used: number; limit: number; message: string };

type ErrorViewProps = {
  error?: string;
  reason?: ErrorReason;
  recoverable?: boolean;
  budgetExceeded?: BudgetExceeded;
  onReset: () => void;
  onRetry?: () => void;
};

export function ErrorView({
  error,
  recoverable,
  budgetExceeded,
  onReset,
  onRetry,
}: ErrorViewProps) {
  if (budgetExceeded) {
    return <BudgetWarning data={budgetExceeded} onReset={onReset} />;
  }
  return (
    <ErrorPanel
      message={error ?? "Research stopped unexpectedly."}
      recoverable={recoverable === true}
      onReset={onReset}
      onRetry={onRetry}
    />
  );
}

function BudgetWarning({
  data,
  onReset,
}: {
  data: BudgetExceeded;
  onReset: () => void;
}) {
  const pct = Math.min(100, (data.tokens_used / data.limit) * 100);
  return (
    <div className="mx-auto mt-10 max-w-xl rounded-lg border border-amber/40 bg-amber/10 p-6 text-amber">
      <div className="mb-2 flex items-center gap-2 font-mono text-[11px] uppercase tracking-caps">
        <WarningGlyph />
        Token budget exceeded
      </div>
      <p className="mb-4 text-sm text-fg">
        Run stopped at {data.tokens_used.toLocaleString()} /{" "}
        {data.limit.toLocaleString()} tokens. The partial report may be incomplete.
      </p>
      <div
        className="mb-4 h-1.5 w-full rounded-full bg-amber/20"
        data-testid="budget-progress"
      >
        <div
          className="h-1.5 rounded-full bg-amber"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex justify-end">
        <button
          onClick={onReset}
          className="rounded-md border border-hairline bg-surface px-3.5 py-1.5 font-mono text-[11px] uppercase tracking-caps text-fg-muted transition hover:border-mint/40 hover:text-mint focus:outline-none focus:ring-2 focus:ring-mint/30"
        >
          New research
        </button>
      </div>
    </div>
  );
}

function ErrorPanel({
  message,
  recoverable,
  onReset,
  onRetry,
}: {
  message: string;
  recoverable: boolean;
  onReset: () => void;
  onRetry?: () => void;
}) {
  return (
    <div className="mx-auto mt-10 max-w-xl rounded-lg border border-coral/40 bg-coral/10 p-6 text-coral">
      <div className="mb-2 flex items-center gap-2 font-mono text-[11px] uppercase tracking-caps">
        <ErrorGlyph />
        Research stopped
      </div>
      <p className="mb-4 text-sm text-fg">{message}</p>
      <div className="flex justify-end gap-2">
        {recoverable && onRetry ? (
          <button
            onClick={onRetry}
            className="rounded-md border border-coral/40 bg-surface px-3.5 py-1.5 font-mono text-[11px] uppercase tracking-caps text-coral transition hover:bg-coral/20 focus:outline-none focus:ring-2 focus:ring-coral/30"
          >
            Try again
          </button>
        ) : null}
        <button
          onClick={onReset}
          className="rounded-md border border-hairline bg-surface px-3.5 py-1.5 font-mono text-[11px] uppercase tracking-caps text-fg-muted transition hover:border-mint/40 hover:text-mint focus:outline-none focus:ring-2 focus:ring-mint/30"
        >
          New research
        </button>
      </div>
    </div>
  );
}

function WarningGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden className="inline-block">
      <path
        d="M8 1.5l7 12H1l7-12z"
        fill="currentColor"
        fillOpacity="0.2"
        stroke="currentColor"
      />
      <path d="M8 6v4" stroke="currentColor" strokeLinecap="round" />
      <circle cx="8" cy="12" r="0.75" fill="currentColor" />
    </svg>
  );
}

function ErrorGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden className="inline-block">
      <circle cx="8" cy="8" r="7" fill="currentColor" fillOpacity="0.15" stroke="currentColor" />
      <path d="M5 5l6 6M11 5l-6 6" stroke="currentColor" strokeLinecap="round" />
    </svg>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
npm test -- ErrorView
```

Expected: all four tests PASS.

- [ ] **Step 5: Run lint + type-check**

```bash
npm run lint
npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/app/research/components/ErrorView.tsx apps/web/app/research/components/ErrorView.test.tsx
git commit -m "feat(web): add ErrorView component with budget + error variants"
```

### Task 6.2: Replace the bottom error bar with inline `ErrorView`

**Files:**
- Modify: `apps/web/app/research/page.tsx`

- [ ] **Step 1: Import `ErrorView`**

At the top of `apps/web/app/research/page.tsx`, add with the other component imports:

```tsx
import { ErrorView } from "./components/ErrorView";
```

- [ ] **Step 2: Replace the `ReportView` section with conditional rendering**

Find the existing block:

```tsx
        <section className="scrollbar-quiet min-w-0 flex-1 overflow-y-auto">
          <ReportView text={state.report} status={state.status} source={state.reportSource} />
        </section>
```

Replace with:

```tsx
        <section className="scrollbar-quiet min-w-0 flex-1 overflow-y-auto">
          {state.status === "error" ? (
            <ErrorView
              error={state.error}
              reason={state.errorReason}
              recoverable={state.errorRecoverable}
              budgetExceeded={state.budgetExceeded}
              onReset={reset}
            />
          ) : (
            <ReportView
              text={state.report}
              status={state.status}
              source={state.reportSource}
            />
          )}
        </section>
```

- [ ] **Step 3: Remove the bottom error bar**

Find and delete this block from `page.tsx`:

```tsx
      {state.error && (
        <div className="border-t border-coral/30 bg-coral/10 px-6 py-3 text-sm text-coral">
          <span className="mr-2 font-medium">Something went wrong.</span>
          {state.error}
        </div>
      )}
```

- [ ] **Step 4: Run all tests**

Run:

```bash
npm test
```

Expected: all tests PASS (reducer + ErrorView + ReportView + sseParser).

- [ ] **Step 5: Manual smoke**

Run from `apps/web/`:

```bash
npm run dev
```

Open http://localhost:3000/research. Submit a question to the backend running with `MAX_TOKENS_PER_RUN=1000` — watch for:

1. Stream starts normally
2. Amber panel appears inline (not bottom bar) when budget is hit
3. Progress bar shows `tokens_used / limit` with amber fill
4. "New research" button resets the view

Also test the error path: stop the backend mid-stream — the client eventually shows the red error panel with a "Try again" button *only* if `recoverable=true` (timeouts). An `internal` error will show no retry button.

- [ ] **Step 6: Run lint + build**

```bash
npm run lint
npm run build
```

Expected: both clean.

- [ ] **Step 7: Commit**

```bash
git add apps/web/app/research/page.tsx
git commit -m "feat(web): replace bottom error bar with inline ErrorView"
```

---

**Chunk 6 review gate:**
- [ ] Full frontend test suite green
- [ ] `next build` clean
- [ ] Manual browser smoke shows amber panel on `budget_exceeded` and red panel on other errors
- [ ] Two new commits

---

## Chunk 7: Docs + Final Verification

### Task 7.1: Add "Enabling tracing locally" to CONTRIBUTING.md

**Files:**
- Modify: `CONTRIBUTING.md`

- [ ] **Step 1: Find the appropriate section**

Open `CONTRIBUTING.md`. Locate the section discussing environment setup (look for `ANTHROPIC_API_KEY` or `.env`). The new section goes after the env-setup block.

- [ ] **Step 2: Add the new section**

Insert:

````markdown
## Enabling tracing locally

Add to `apps/api/.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...      # from smith.langchain.com → Settings → API Keys
LANGCHAIN_PROJECT=chat-agents  # project name in LangSmith
```

The app re-exports these to `os.environ` at startup (same pattern as `ANTHROPIC_API_KEY`), so LangChain picks them up automatically. Tracing is disabled by default — omit `LANGCHAIN_TRACING_V2` or set it to `false`.

Each `/research` trace carries `request_id`, `thread_id`, and `prompt_versions` metadata, and is tagged with the active `LLM_PROVIDER`. Supervisor + subagent spans are nested under the top-level run automatically.
````

- [ ] **Step 3: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add 'Enabling tracing locally' section"
```

### Task 7.2: Full cross-cutting verification

- [ ] **Step 1: Backend — full gate**

Run from `apps/api/`:

```bash
ruff check .
ruff format --check .
mypy app/
pytest
```

Expected: all clean / green.

- [ ] **Step 2: Frontend — full gate**

Run from `apps/web/`:

```bash
npm run lint
npm run format:check
npm test
npm run build
```

Expected: all clean / green.

- [ ] **Step 3: Live smoke test**

Two terminals.

**Terminal A** (backend):

```bash
cd apps/api
# temporarily set a very low budget for the smoke
MAX_TOKENS_PER_RUN=1000 uvicorn app.main:app --port 8000 --reload
```

Watch the console — the first request should emit JSON log lines with `request_id`, `thread_id`, `prompt_versions`.

**Terminal B** (frontend):

```bash
cd apps/web
npm run dev
```

Open http://localhost:3000/research and submit a real question. Verify:

1. ✅ Backend stdout shows a JSON log line `research.invoked` with `request_id`, `thread_id`, `prompt_versions` all bound from context.
2. ✅ The SSE stream eventually emits a `budget_exceeded` event (visible in DevTools → Network → EventStream for `/api/research`).
3. ✅ The UI shows the inline amber panel with progress bar — **no bottom bar**.
4. ✅ The backend log includes a `research.budget_exceeded` line with `tokens_used` and `limit`.
5. ✅ Clicking "New research" resets to the question form.

Stop both servers.

- [ ] **Step 4: LangSmith check (optional, only if tracing creds available)**

With valid `LANGCHAIN_*` keys set in `.env`, re-run a normal request (raise `MAX_TOKENS_PER_RUN` back to 200_000). Visit smith.langchain.com → `chat-agents` project. Verify:

- The most recent run shows a tree with the supervisor node + `researcher` / `critic` subagent spans
- Metadata panel includes `request_id`, `prompt_versions`
- Tags include `anthropic` (or whatever `LLM_PROVIDER` is set to)

If tracing creds are not available locally, skip this step — it's covered by the manual CONTRIBUTING.md instructions.

- [ ] **Step 5: Open the PR**

```bash
git push -u origin <branch-name>
# Base is v1 (not main) because v1 carries the Journal-theme UI the ErrorView
# styling depends on. `--base v1` is required on gh pr create.
gh pr create --base v1 --title "feat(api,web): langsmith tracing + structlog + token budget" --body "$(cat <<'EOF'
## Summary
- Adds optional LangSmith tracing via `LANGCHAIN_*` env re-export
- Structured JSON logs via structlog with `request_id`/`thread_id`/`prompt_versions` bound through contextvars
- Token budget guard aborts runs over `MAX_TOKENS_PER_RUN` with a new `budget_exceeded` SSE event
- Replaces bottom error bar with inline `ErrorView` (amber warning / red error variants)

## Base
Cut from and targets `v1`, not `main`. The Journal-theme UI landed on `v1` in `ff3bd59` and has not yet merged to `main`; `ErrorView` is styled against that palette.

## Test plan
- [ ] `cd apps/api && pytest` green
- [ ] `cd apps/api && ruff check . && ruff format --check . && mypy app/` clean
- [ ] `cd apps/web && npm test && npm run build` green
- [ ] Manual: run `/research` with `MAX_TOKENS_PER_RUN=1000` → UI shows amber budget panel inline, backend emits JSON logs with bound context

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Stop before merging — wait for human review.

---

## Acceptance Criteria Checklist

Derived from the spec §10. Each must be satisfied before the PR merges:

- [ ] LangSmith shows a trace for every `/research` call, including supervisor + subagent hierarchy
- [ ] All application logs in `routers/research.py` are structured JSON with `thread_id`, `request_id`, `prompt_versions` bound from context
- [ ] Token budget guard aborts runs over `MAX_TOKENS_PER_RUN`; emits `budget_exceeded` SSE event followed by `stream_end(final_report_source="error")`
- [ ] `budget_exceeded` renders inline in amber/warning style; `error` renders inline in red/coral style
- [ ] "Try again" button appears only for `recoverable: true` errors
- [ ] Bottom error bar removed from `page.tsx`
- [ ] All unit + e2e tests pass
- [ ] `ruff check . && ruff format --check . && mypy app/` clean
- [ ] `tsc` via `next build` clean; `npm test` green

---

## Out of Scope (explicitly)

Per spec §11: Langfuse, Prometheus, auth, rate limiting, client-side logger / `request_id`, the pre-existing `memory_updated` event gap. Do not add/remove those in this plan.
