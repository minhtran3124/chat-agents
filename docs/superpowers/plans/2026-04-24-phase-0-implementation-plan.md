# Phase 0: Stabilize SSE Contract — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the `/research` SSE contract so `stream_end` fires on every terminal path, runs can't exceed `RESEARCH_TIMEOUT_S` (default 500 s), the orphan `memory_updated` event is removed, and a `CHANGELOG.md` exists for future phase entries. Phase 0 is pure stabilization — no new product capabilities.

**Architecture:** Python 3.11+ `asyncio.timeout` wraps `agent.astream` inside a `try/except/finally` block where `finally` unconditionally yields `stream_end`. A sanitized per-reason error catalog (`ErrorReason` Literal on both Python + TypeScript sides) replaces raw `str(e)` leakage. Pydantic `Field` with bounds validates the new setting. The frontend reducer adds a no-op branch when `stream_end.final_report_source === "error"` so the preceding `error` event's `status: "error"` is preserved. No DB changes, no new dependencies, no version bump.

**Tech Stack:**
- Backend: Python 3.11+, FastAPI 0.115+, sse-starlette, pydantic 2.7+, pydantic-settings, pytest, pytest-asyncio (auto mode), `asyncio.timeout` (stdlib 3.11+)
- Frontend: TypeScript strict, Next.js 14.2 App Router, React 18, vitest + @testing-library/react
- Spec source: [`docs/superpowers/specs/2026-04-24-phase-0-stabilize-sse-contract-design.md`](../specs/2026-04-24-phase-0-stabilize-sse-contract-design.md)
- GitHub: [Issue #2](https://github.com/minhtran3124/chat-agents/issues/2), [Milestone #1](https://github.com/minhtran3124/chat-agents/milestone/1)

**Target branch:** `fix/phase-0-stabilize-sse-contract` off `v1` (the active development line for this repo; `main` is not the base for current work)

**Estimated total steps:** ~55, grouped into 12 tasks across 4 chunks. Each step is 2–5 min.

---

## Chunk 0: Preflight & branch setup

### Task 0.1: Create branch and confirm environment

**Files:**
- Touch: none (git operations only)

- [ ] **Step 0.1.1: Confirm you are on the repo root and branch `v1` exists**

Run from repo root `chat-agents/`:

```bash
git rev-parse --show-toplevel
git branch -a | grep -E '(^\*|v1)'
git remote -v
```

Expected output:
- First line prints the absolute repo path.
- Second section lists `v1` among local/remote branches.
- Third section shows the remote name — this plan assumes it is **`github`** (as in `git@github.tranhuuminh3124.com:minhtran3124/chat-agents.git`). If your remote is `origin` or another name, substitute that name everywhere you see `github` in later git commands (Steps 0.1.3, 4.6.1, Appendix A).

**Important**: this repo's active development line is `v1`, not `main`. The implementation branch is created off `v1`, and the PR targets `v1`. `main` may be a stable/release pointer but is not the Phase 0 base.

If `v1` is not present locally, fetch it: `git fetch <remote> v1:v1`.

- [ ] **Step 0.1.2: Ensure working tree is clean for the spec/roadmap files**

```bash
git status --short
```

Expected: any changes under `docs/superpowers/specs/` or `reseachers/` should already be committed (they were, during brainstorming). Other untracked files under `.claude/` or `apps/web/pnpm-lock.yaml` are unrelated and can remain untracked.

If you see uncommitted changes on `apps/api/` or `apps/web/lib/` from a previous session, **stop and investigate** — Phase 0 must start from a known-clean slate.

- [ ] **Step 0.1.3: Create and check out the implementation branch**

```bash
git checkout v1
git pull github v1
git checkout -b fix/phase-0-stabilize-sse-contract
git status
```

Expected: `On branch fix/phase-0-stabilize-sse-contract` with a clean working tree. The branch is now based on the latest tip of `v1`.

- [ ] **Step 0.1.4: Verify backend test suite is currently green on `v1`'s tip**

```bash
cd apps/api && pytest -q 2>&1 | tail -5
```

Expected: all tests pass. If not, **stop** — a red baseline means you cannot detect Phase 0 regressions.

- [ ] **Step 0.1.5: Verify frontend test suite is currently green**

```bash
cd apps/web && npm test -- --run 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 0.1.6: Confirm `deepagents >= 0.5.2` is pinned**

```bash
grep 'deepagents' apps/api/pyproject.toml
```

Expected: `"deepagents>=0.5.2",`. If it shows a lower pin, stop — the spec assumes 0.5.2+ is in place.

### Task 0.2: Grep baseline for `memory_updated`

**Files:**
- Touch: none (read-only discovery)

- [ ] **Step 0.2.1: Capture the starting references so you can verify removal at the end**

```bash
grep -rn "memory_updated" apps/ --include="*.py" --include="*.ts" --include="*.tsx"
```

Expected exactly 3 hits:
- `apps/api/app/streaming/events.py:62` (factory declaration)
- `apps/api/app/streaming/events.py:63` (factory body)
- `apps/web/lib/types.ts:32` (SSEEventMap entry)

If you see more than 3 hits, capture the list — every one of them must be removed by the end of Chunk 1.

---

## Chunk 1: Backend contract foundation — settings + events factory

### Task 1.1: Add `RESEARCH_TIMEOUT_S` setting with bounds validation

**Files:**
- Modify: `apps/api/app/config/settings.py`
- Test: `apps/api/tests/unit/test_settings.py`

- [ ] **Step 1.1.1: Read the existing settings test file to match its patterns**

```bash
cat apps/api/tests/unit/test_settings.py
```

Note the patterns: how `Settings(...)` is instantiated in tests, what fixtures exist, and how failures are asserted (likely `pytest.raises(ValidationError)`).

- [ ] **Step 1.1.2: Write three failing tests for the new field**

Append to `apps/api/tests/unit/test_settings.py`:

```python
import pytest
from pydantic import ValidationError

from app.config.settings import Settings


@pytest.mark.unit
def test_research_timeout_s_rejects_below_minimum():
    with pytest.raises(ValidationError) as exc:
        Settings(
            LLM_PROVIDER="anthropic",
            ANTHROPIC_API_KEY="sk-ant-test",
            TAVILY_API_KEY="tvly-test",
            RESEARCH_TIMEOUT_S=5,
        )
    assert "RESEARCH_TIMEOUT_S" in str(exc.value)


@pytest.mark.unit
def test_research_timeout_s_rejects_above_maximum():
    with pytest.raises(ValidationError) as exc:
        Settings(
            LLM_PROVIDER="anthropic",
            ANTHROPIC_API_KEY="sk-ant-test",
            TAVILY_API_KEY="tvly-test",
            RESEARCH_TIMEOUT_S=7200,
        )
    assert "RESEARCH_TIMEOUT_S" in str(exc.value)


@pytest.mark.unit
def test_research_timeout_s_default_is_500():
    s = Settings(
        LLM_PROVIDER="anthropic",
        ANTHROPIC_API_KEY="sk-ant-test",
        TAVILY_API_KEY="tvly-test",
    )
    assert s.RESEARCH_TIMEOUT_S == 500
```

If the existing test file already imports `Settings` or has a shared fixture for required API keys, **use that pattern** instead of repeating the kwargs. Check `apps/api/tests/conftest.py` for fixtures too.

- [ ] **Step 1.1.3: Run the new tests — verify they FAIL**

```bash
cd apps/api && pytest tests/unit/test_settings.py -v -k research_timeout 2>&1 | tail -20
```

Expected: 3 failures (attribute `RESEARCH_TIMEOUT_S` does not exist, or `AttributeError`). This confirms the tests would catch missing implementation.

- [ ] **Step 1.1.4: Add the `RESEARCH_TIMEOUT_S` field to `Settings`**

In `apps/api/app/config/settings.py`, insert the field after `COMPRESSION_DETECTION_RATIO` (around line 28) and before `LOG_LEVEL`:

```python
    RESEARCH_TIMEOUT_S: int = Field(
        default=500,
        ge=10,
        le=3600,
        description=(
            "Maximum wall-clock seconds for a single /research run before "
            "asyncio.timeout cancels it and emits a timeout error."
        ),
    )
```

Confirm `Field` is already imported (line 4: `from pydantic import Field, model_validator`). If not, add `Field` to that import.

- [ ] **Step 1.1.5: Run the tests — verify they PASS**

```bash
cd apps/api && pytest tests/unit/test_settings.py -v -k research_timeout 2>&1 | tail -20
```

Expected: 3 passes.

- [ ] **Step 1.1.6: Run the full unit test suite to catch regressions**

```bash
cd apps/api && pytest -m unit -q 2>&1 | tail -5
```

Expected: all unit tests pass.

- [ ] **Step 1.1.7: Run linters**

```bash
cd apps/api && ruff check app/config/settings.py tests/unit/test_settings.py && ruff format --check app/config/settings.py tests/unit/test_settings.py && mypy app/config/settings.py
```

Expected: no errors.

- [ ] **Step 1.1.8: Commit**

```bash
git add apps/api/app/config/settings.py apps/api/tests/unit/test_settings.py
git commit -m "$(cat <<'EOF'
feat(api): add RESEARCH_TIMEOUT_S setting with bounds validation

Introduces a pydantic Field (default 500, ge=10, le=3600) that will back
the asyncio.timeout guard around /research agent streaming. Validation
fail-fasts at startup for out-of-bounds values — matches the existing
_resolve_and_validate pattern for missing API keys.

Part of Phase 0; refs #2.
EOF
)"
```

### Task 1.2: Introduce `ErrorReason`, `FinalReportSource`, and `ERROR_MESSAGES` in `events.py`

**Files:**
- Modify: `apps/api/app/streaming/events.py`
- Test: `apps/api/tests/unit/test_events.py`

- [ ] **Step 1.2.1: Check the existing events test file and its imports**

```bash
cat apps/api/tests/unit/test_events.py
grep -n "^import\|^from" apps/api/tests/unit/test_events.py
```

Match the import and assertion style. If `import json` and `from app.streaming import events` are NOT already at the top of the file, add them as part of the later test-writing steps (1.2.2, 1.3.1, 1.4.1) — don't introduce them mid-file.

- [ ] **Step 1.2.2: Write failing test for the new catalog + type aliases**

Append to `apps/api/tests/unit/test_events.py`:

```python
from app.streaming.events import (
    ERROR_MESSAGES,
    ErrorReason,
    FinalReportSource,
)


@pytest.mark.unit
def test_error_messages_catalog_covers_both_reasons():
    assert set(ERROR_MESSAGES.keys()) == {"timeout", "internal"}
    for reason, message in ERROR_MESSAGES.items():
        assert isinstance(message, str)
        assert len(message) > 10  # non-empty, human-readable

@pytest.mark.unit
def test_error_reason_type_alias_values():
    # Purely a smoke check: the Literal should accept both valid values at
    # runtime via typing.get_args (mypy does the real enforcement).
    from typing import get_args
    assert set(get_args(ErrorReason)) == {"timeout", "internal"}

@pytest.mark.unit
def test_final_report_source_widened_to_include_error():
    from typing import get_args
    assert set(get_args(FinalReportSource)) == {"stream", "file", "error"}
```

- [ ] **Step 1.2.3: Run — verify FAIL**

```bash
cd apps/api && pytest tests/unit/test_events.py -v -k 'catalog or type_alias or widened' 2>&1 | tail -20
```

Expected: `ImportError: cannot import name 'ERROR_MESSAGES'` (or similar) on all three tests.

- [ ] **Step 1.2.4: Add the type aliases + catalog to `events.py`**

In `apps/api/app/streaming/events.py`, after the existing imports (top of file, before `def _sse`):

```python
ErrorReason = Literal["timeout", "internal"]
FinalReportSource = Literal["stream", "file", "error"]

ERROR_MESSAGES: dict[ErrorReason, str] = {
    "timeout": (
        "Research timed out. Please try again with a simpler question "
        "or contact support if this persists."
    ),
    "internal": (
        "Research failed due to an internal error. Please try again shortly."
    ),
}
```

`Literal` is already imported from `typing` (line 3).

- [ ] **Step 1.2.5: Run — verify PASS**

```bash
cd apps/api && pytest tests/unit/test_events.py -v -k 'catalog or type_alias or widened' 2>&1 | tail -20
```

Expected: 3 passes.

- [ ] **Step 1.2.6: Commit**

```bash
git add apps/api/app/streaming/events.py apps/api/tests/unit/test_events.py
git commit -m "$(cat <<'EOF'
feat(api): add ErrorReason, FinalReportSource, and ERROR_MESSAGES catalog

Introduces the typed contract primitives used by the refactored error()
factory and widened stream_end() in the next step. The static message
catalog is what prevents raw str(e) from leaking to the SSE client.

Part of Phase 0; refs #2.
EOF
)"
```

### Task 1.3: Refactor `error()` factory to take `reason` only

**Files:**
- Modify: `apps/api/app/streaming/events.py`
- Test: `apps/api/tests/unit/test_events.py`

- [ ] **Step 1.3.1: Write failing tests for the new `error()` signature**

Append to `apps/api/tests/unit/test_events.py`:

```python
@pytest.mark.unit
def test_error_factory_timeout_shape():
    ev = events.error("timeout")
    assert ev["event"] == "error"
    data = json.loads(ev["data"])
    assert data["reason"] == "timeout"
    assert data["recoverable"] is True
    assert data["message"] == ERROR_MESSAGES["timeout"]


@pytest.mark.unit
def test_error_factory_internal_shape():
    ev = events.error("internal")
    assert ev["event"] == "error"
    data = json.loads(ev["data"])
    assert data["reason"] == "internal"
    assert data["recoverable"] is False
    assert data["message"] == ERROR_MESSAGES["internal"]
```

Ensure `import json` and `from app.streaming import events` are imported at the top of the test file (or adjust per existing conventions).

- [ ] **Step 1.3.2: Run — verify FAIL**

```bash
cd apps/api && pytest tests/unit/test_events.py -v -k 'error_factory' 2>&1 | tail -20
```

Expected: failures — likely `TypeError` (old signature requires `message: str` positionally) or `KeyError` on `reason`.

- [ ] **Step 1.3.3: Refactor `error()` in `events.py`**

Replace the existing `error` function (around line 70–71):

```python
def error(reason: ErrorReason) -> dict:
    return _sse("error", {
        "message":     ERROR_MESSAGES[reason],
        "reason":      reason,
        "recoverable": reason == "timeout",
    })
```

- [ ] **Step 1.3.4: Run — verify PASS**

```bash
cd apps/api && pytest tests/unit/test_events.py -v -k 'error_factory' 2>&1 | tail -20
```

Expected: 2 passes.

- [ ] **Step 1.3.5: Fix any other callers of `events.error(...)` that broke**

```bash
grep -rn "events.error(" apps/api --include="*.py"
```

Expected callers: `apps/api/app/routers/research.py:120` (will be rewritten in Chunk 2 — leave it for now, just note the break). Any test file callers should pass `reason` values now. If unit tests break here, fix them.

If `pytest -m unit` currently fails because of the router's stale call, that's expected — it'll be fixed in Task 2.1. For now, scope the assertion to the unit test suite minus router tests:

```bash
cd apps/api && pytest tests/unit/test_events.py tests/unit/test_settings.py -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 1.3.6: Commit**

```bash
git add apps/api/app/streaming/events.py apps/api/tests/unit/test_events.py
git commit -m "$(cat <<'EOF'
refactor(api): error() SSE factory now takes reason, derives everything

error() signature changes from (message: str, recoverable: bool) to
(reason: ErrorReason). Message comes from ERROR_MESSAGES catalog;
recoverable derives from reason ("timeout" → true, "internal" → false).
This makes it structurally impossible to leak str(e) to the SSE client.

Router caller (research.py) still uses the old shape and will be
updated in the next commit as part of the try/except/finally refactor.

Part of Phase 0; refs #2.
EOF
)"
```

### Task 1.4: Widen `stream_end()` `final_report_source` Literal

**Files:**
- Modify: `apps/api/app/streaming/events.py`
- Test: `apps/api/tests/unit/test_events.py`

- [ ] **Step 1.4.1: Write failing test**

Append to `apps/api/tests/unit/test_events.py`:

```python
@pytest.mark.unit
def test_stream_end_accepts_error_as_final_report_source():
    ev = events.stream_end(
        final_report="",
        usage={},
        versions_used={"main": "v3"},
        final_report_source="error",
    )
    assert ev["event"] == "stream_end"
    data = json.loads(ev["data"])
    assert data["final_report_source"] == "error"
    assert data["final_report"] == ""
```

- [ ] **Step 1.4.2: Run — verify FAIL**

```bash
cd apps/api && pytest tests/unit/test_events.py -v -k 'stream_end_accepts_error' 2>&1 | tail -20
```

Expected: failure under mypy (but pytest will still run; the runtime Literal is permissive). If the test passes at runtime, that's fine — it's establishing the contract expected by downstream code. Move on.

(The real enforcement here is `mypy`, not runtime. We'll run mypy in step 1.4.4.)

- [ ] **Step 1.4.3: Widen the Literal in `stream_end()`**

In `apps/api/app/streaming/events.py`, change the signature around line 75:

```python
def stream_end(
    final_report: str,
    usage: dict[str, Any],
    versions_used: dict[str, str],
    final_report_source: FinalReportSource = "stream",
) -> dict:
    return _sse(
        "stream_end",
        {
            "final_report": final_report,
            "usage": usage,
            "versions_used": versions_used,
            "final_report_source": final_report_source,
        },
    )
```

Replaced `Literal["stream", "file"]` with the new `FinalReportSource` alias defined in Task 1.2.

- [ ] **Step 1.4.4: Run tests + mypy**

```bash
cd apps/api && pytest tests/unit/test_events.py -q && mypy app/streaming/events.py
```

Expected: tests pass; mypy clean.

- [ ] **Step 1.4.5: Commit**

```bash
git add apps/api/app/streaming/events.py apps/api/tests/unit/test_events.py
git commit -m "$(cat <<'EOF'
feat(api): widen stream_end final_report_source to include \"error\"

final_report_source Literal now accepts "stream" | "file" | "error".
The "error" variant is the canonical terminal signal for failed runs,
emitted from the finally block in the research router (next commit).

Part of Phase 0; refs #2.
EOF
)"
```

### Task 1.5: Remove the orphan `memory_updated` factory

**Files:**
- Modify: `apps/api/app/streaming/events.py`
- Modify (if any caller found): `apps/api/tests/unit/test_events.py`

- [ ] **Step 1.5.1: Re-confirm nothing calls `events.memory_updated` in Python**

```bash
grep -rn "memory_updated" apps/api --include="*.py"
```

Expected: exactly 2 hits (lines 62 and 63 of `events.py`). If there are test references, list them — they must be removed in the same commit.

- [ ] **Step 1.5.2: Delete the factory function**

In `apps/api/app/streaming/events.py`, remove these two lines (currently around 62–63):

```python
def memory_updated(namespace: str, key: str) -> dict:
    return _sse("memory_updated", {"namespace": namespace, "key": key})
```

Leave a blank line where the function was if the file's formatter prefers double blanks between top-level defs.

- [ ] **Step 1.5.3: Remove any test references**

If Step 1.5.1 showed test files referencing `memory_updated`, open them and delete those tests (they document a feature that no longer exists).

- [ ] **Step 1.5.4: Verify zero remaining Python references**

```bash
grep -rn "memory_updated" apps/api --include="*.py"
```

Expected: **no output**.

- [ ] **Step 1.5.5: Run the events test suite + mypy + ruff**

```bash
cd apps/api && pytest tests/unit/test_events.py -q && mypy app/streaming/events.py && ruff check app/streaming/events.py
```

Expected: all green.

- [ ] **Step 1.5.6: Commit**

```bash
git add apps/api/app/streaming/events.py apps/api/tests/unit/test_events.py
git commit -m "$(cat <<'EOF'
chore(api): remove orphan memory_updated SSE factory

memory_updated has zero emitters in the backend and no reducer case in
the frontend — it was declared in SSEEventMap but never plumbed. When
real semantic memory lands (post Phase 6), a new memory_operation event
with a mem0-native shape will replace this slot. See roadmap §10.

Frontend removal follows in Chunk 3.

Part of Phase 0; refs #2.
EOF
)"
```

### Task 1.6: Chunk 1 verification gate

**Files:** (no changes — verification only)

- [ ] **Step 1.6.1: Run the full backend test suite**

```bash
cd apps/api && pytest -q 2>&1 | tail -10
```

Expected: all tests pass **except** possibly the existing router/e2e tests, which rely on the old `events.error(message, recoverable)` signature — those will be fixed in Chunk 2. If router tests fail with `TypeError` on `events.error`, that's the expected intermediate state. Note the number of failures so you can verify they drop to zero after Chunk 2.

- [ ] **Step 1.6.2: Run ruff + mypy across all touched files**

```bash
cd apps/api && ruff check app/ tests/ && ruff format --check app/ tests/ && mypy app/
```

Expected: green across the board.

- [ ] **Step 1.6.3: Confirm git log for Chunk 1**

```bash
git log --oneline v1..HEAD
```

Expected: 5 commits in the order feat(settings) → feat(ErrorReason catalog) → refactor(error factory) → feat(stream_end widen) → chore(remove memory_updated).

---

## Chunk 2: Backend router refactor + e2e timeout test

### Task 2.1: Refactor `research.py` router to `try/except/finally` with `asyncio.timeout`

**Files:**
- Modify: `apps/api/app/routers/research.py`
- Test: `apps/api/tests/unit/test_research_router.py`

- [ ] **Step 2.1.1: Reconnaissance — capture existing patterns before writing any test**

Run all of these before writing new code; note exact names and patterns:

```bash
cat apps/api/tests/unit/test_research_router.py
cat apps/api/tests/conftest.py
grep -n "^async def\|^def\|@router\." apps/api/app/routers/research.py
grep -rn "async_client\|AsyncClient\|ASGITransport" apps/api/tests --include="*.py"
grep -n "ok_agent\|failing_agent\|slow_agent\|collect_" apps/api/tests --include="*.py" -r
```

Record:
- The actual name of the router handler function in `research.py` (likely `research(...)` on line 32 — used in place of `research_handler` below).
- Whether `collect_sse_events` (or equivalent) already exists in `conftest.py` or a helpers file.
- Whether `ok_agent_factory` / `failing_agent_factory` / `slow_agent_factory` already exist.
- The exact name of the HTTP client fixture (`async_client` / `client` / `api_client`) and which transport it uses.
- The **actual shape** yielded by `EventSourceResponse.body_iterator` — run a quick REPL probe if unsure, because `sse-starlette` versions vary (some yield `ServerSentEvent` objects with `.event` / `.data` attributes, some yield raw dict, some yield pre-formatted strings).

If any of the fixtures below are already present, **reuse them**; do not duplicate. If `collect_sse_events` shape doesn't match what's shown in Step 2.1.2, adjust the helper to match reality — the test assertions (event names, data shapes) are the real contract, not the parsing glue.

- [ ] **Step 2.1.2: Write failing test — generator emits stream_end on internal exception**

Append to `apps/api/tests/unit/test_research_router.py`. **Before pasting**, substitute `research_handler` with the actual handler name you noted in Step 2.1.1 (likely just `research`). Match the existing test file's imports and `ResearchRequest` construction pattern.

```python
@pytest.mark.unit
async def test_generator_emits_stream_end_on_internal_exception(
    failing_agent_factory,  # fixture — see Step 2.1.3
    monkeypatch,
):
    """DESIGN: Per spec §4.4, an uncaught exception must produce
    error{reason:"internal"} followed by stream_end{source:"error"}."""
    from app.routers.research import research as research_handler  # rename-local

    agent = failing_agent_factory(RuntimeError("boom"))
    monkeypatch.setattr(
        "app.routers.research.build_research_agent",
        lambda **kw: agent,
    )

    payload = ResearchRequest(question="anything")
    resp = await research_handler(payload)  # EventSourceResponse
    collected = await collect_sse_events(resp)

    event_names = [e["event"] for e in collected]
    assert event_names[0] == "stream_start"
    assert "error" in event_names
    assert event_names[-1] == "stream_end"

    error_ev = next(e for e in collected if e["event"] == "error")
    error_data = json.loads(error_ev["data"])
    assert error_data["reason"] == "internal"
    assert error_data["recoverable"] is False

    end_ev = collected[-1]
    end_data = json.loads(end_ev["data"])
    assert end_data["final_report_source"] == "error"
    assert end_data["final_report"] == ""

    # error comes before stream_end (spec §5.1)
    assert event_names.index("error") < event_names.index("stream_end")
```

If the existing test file already has a `failing_agent_factory` fixture or equivalent, use it. Otherwise, add to `apps/api/tests/conftest.py`:

```python
@pytest.fixture
def failing_agent_factory():
    """Factory for fake agents whose .astream raises the given exception."""
    def _make(exception: Exception):
        class _FailingAgent:
            async def astream(self, *_args, **_kwargs):
                raise exception
                yield  # unreachable but marks this as an async generator

            async def aget_state(self, *_args, **_kwargs):
                return None

        return _FailingAgent()

    return _make


async def collect_sse_events(event_source_response) -> list[dict]:
    """Drains an EventSourceResponse's generator into a list of {"event", "data"} dicts.

    NOTE: `sse-starlette` may yield different shapes across versions —
    pre-formatted strings, ServerSentEvent objects, or dicts. Adjust the
    `_normalize(item)` helper below to match what your installed version
    actually yields (from the reconnaissance in Step 2.1.1).
    """
    gen = event_source_response.body_iterator

    def _normalize(item) -> dict:
        # Common cases:
        if isinstance(item, dict):
            return {"event": item.get("event", ""), "data": item.get("data", "")}
        # ServerSentEvent object with attributes
        if hasattr(item, "event") and hasattr(item, "data"):
            return {"event": item.event, "data": item.data}
        # Pre-formatted "event: foo\ndata: {...}\n\n" string
        if isinstance(item, (str, bytes)):
            text = item.decode() if isinstance(item, bytes) else item
            event_line = next((ln for ln in text.splitlines() if ln.startswith("event: ")), "")
            data_line = next((ln for ln in text.splitlines() if ln.startswith("data: ")), "")
            return {
                "event": event_line.removeprefix("event: ").strip(),
                "data": data_line.removeprefix("data: ").strip(),
            }
        raise AssertionError(f"Unrecognized SSE item shape: {type(item)!r}")

    return [_normalize(item) async for item in gen]
```

- [ ] **Step 2.1.3: Run — verify FAIL**

```bash
cd apps/api && pytest tests/unit/test_research_router.py -v -k 'on_internal_exception' 2>&1 | tail -30
```

Expected: failure — likely because the existing generator doesn't yield `stream_end` on exception, or because `events.error` signature mismatch propagates.

- [ ] **Step 2.1.4: Write failing test — generator emits stream_end on timeout**

Append to `apps/api/tests/unit/test_research_router.py`:

```python
@pytest.mark.unit
async def test_generator_emits_stream_end_on_timeout(
    slow_agent_factory,
    monkeypatch,
):
    """DESIGN: Per spec §4.4, exceeding RESEARCH_TIMEOUT_S must produce
    error{reason:"timeout", recoverable:True} then stream_end{source:"error"}."""
    import app.config.settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "RESEARCH_TIMEOUT_S", 1)
    agent = slow_agent_factory(sleep_s=5)
    monkeypatch.setattr(
        "app.routers.research.build_research_agent",
        lambda **kw: agent,
    )

    payload = ResearchRequest(question="anything")
    resp = await research_handler(payload)
    collected = await collect_sse_events(resp)

    event_names = [e["event"] for e in collected]
    assert event_names[0] == "stream_start"
    assert event_names[-1] == "stream_end"

    error_ev = next(e for e in collected if e["event"] == "error")
    error_data = json.loads(error_ev["data"])
    assert error_data["reason"] == "timeout"
    assert error_data["recoverable"] is True

    end_data = json.loads(collected[-1]["data"])
    assert end_data["final_report_source"] == "error"
```

Add to `apps/api/tests/conftest.py`:

```python
@pytest.fixture
def slow_agent_factory():
    """Factory for fake agents whose .astream sleeps longer than RESEARCH_TIMEOUT_S."""
    def _make(sleep_s: float = 5.0):
        class _SlowAgent:
            async def astream(self, *_args, **_kwargs):
                await asyncio.sleep(sleep_s)
                yield "values", {}

            async def aget_state(self, *_args, **_kwargs):
                return None

        return _SlowAgent()

    return _make
```

Ensure `import asyncio` at the top of `conftest.py`.

- [ ] **Step 2.1.5: Run — verify FAIL**

```bash
cd apps/api && pytest tests/unit/test_research_router.py -v -k 'on_timeout' 2>&1 | tail -30
```

Expected: failure — the router has no timeout guard.

- [ ] **Step 2.1.6: Write failing test — success path still works and NO error is emitted**

Append to `apps/api/tests/unit/test_research_router.py`:

```python
@pytest.mark.unit
async def test_generator_success_path_no_error_event(
    ok_agent_factory,  # reuse existing fixture if present
    monkeypatch,
):
    """Regression guard: success-path stream_end must have source="stream"
    and NO error event is emitted."""
    agent = ok_agent_factory(report_text="x" * 300)  # > MIN_STREAM_REPORT_CHARS
    monkeypatch.setattr(
        "app.routers.research.build_research_agent",
        lambda **kw: agent,
    )

    payload = ResearchRequest(question="hello")
    resp = await research_handler(payload)
    collected = await collect_sse_events(resp)

    event_names = [e["event"] for e in collected]
    assert "error" not in event_names
    assert event_names[-1] == "stream_end"

    end_data = json.loads(collected[-1]["data"])
    assert end_data["final_report_source"] == "stream"
    assert len(end_data["final_report"]) >= 300
```

If `ok_agent_factory` doesn't exist, stub it in `conftest.py` to yield a single text_delta then complete. Exact shape depends on how the existing tests fabricate "successful" agent streams — match that pattern.

- [ ] **Step 2.1.7: Run all 3 new tests — verify they FAIL (expected for two, may already-pass for success)**

```bash
cd apps/api && pytest tests/unit/test_research_router.py -v -k 'generator_' 2>&1 | tail -30
```

Expected: the internal and timeout tests fail; the success-path test may already pass (but the `events.error` signature change from Task 1.3 may have broken the existing success test — you'll see that first).

- [ ] **Step 2.1.8: Refactor the router generator**

Rewrite `apps/api/app/routers/research.py`. The full target is in the spec [§5.1](../specs/2026-04-24-phase-0-stabilize-sse-contract-design.md#51-target-generator-body). Copy that body in.

Key edits vs. current file:
- Add `import asyncio` at the top (if not already present).
- Add `from app.config.settings import settings`.
- Add `from app.streaming.events import ErrorReason, FinalReportSource`.
- Replace the entire `async def generator()` body with the try/except/finally version from the spec.
- Ensure `error_reason: ErrorReason | None = None` and the two accumulators are declared immediately after `yield events.stream_start(thread_id)`.

- [ ] **Step 2.1.9: Run the 3 new tests — verify they PASS**

```bash
cd apps/api && pytest tests/unit/test_research_router.py -v -k 'generator_' 2>&1 | tail -30
```

Expected: 3 passes.

- [ ] **Step 2.1.10: Run ALL router tests (catches regressions on fallback-draft and other existing cases)**

```bash
cd apps/api && pytest tests/unit/test_research_router.py -v 2>&1 | tail -30
```

Expected: all pass, including the existing `fallback_draft` test (spec §2.2 says that logic is unchanged on success path).

**Heads-up**: Chunk 1 Task 1.3 already refactored `events.error()` to take `reason` instead of `(message, recoverable)`. If any pre-existing router test constructs expected events via `events.error("some string")`, it was broken at the start of Chunk 2 and must be updated to the new signature as part of THIS step. This is part of Chunk 2's job — do not defer. Run `grep -n 'events\.error(' apps/api/tests` to find all call sites and reconcile each one.

- [ ] **Step 2.1.11: Run ruff + mypy on the router**

```bash
cd apps/api && ruff check app/routers/research.py && ruff format --check app/routers/research.py && mypy app/routers/research.py
```

Expected: green.

- [ ] **Step 2.1.12: Commit**

```bash
git add apps/api/app/routers/research.py apps/api/tests/unit/test_research_router.py apps/api/tests/conftest.py
git commit -m "$(cat <<'EOF'
fix(api): try/except/finally around agent.astream; always emit stream_end

Every /research terminal path (success, timeout, unhandled exception)
now emits stream_end — clients can rely on it to drive the reducer's
"done" state. asyncio.timeout(settings.RESEARCH_TIMEOUT_S) wraps the
whole generator body (astream loop, compression check, aget_state,
draft-fallback). On timeout or exception: emit error(reason) first,
then stream_end with final_report_source="error" in a finally block.

Fixes the pre-existing UI-stuck-in-streaming bug reported in #2.

Part of Phase 0; closes the core bug in #2.
EOF
)"
```

### Task 2.2: End-to-end timeout test

**Files:**
- Test: `apps/api/tests/e2e/test_research_endpoint.py`

- [ ] **Step 2.2.1: Read the existing e2e file and identify the HTTP client fixture name**

```bash
cat apps/api/tests/e2e/test_research_endpoint.py
grep -n "def .*client\|AsyncClient\|ASGITransport" apps/api/tests/conftest.py apps/api/tests/e2e/*.py
```

Before writing the new test, **confirm the exact name of the HTTP client fixture** (commonly `async_client`, `client`, `api_client`, or `http_client`). Use the same name in Step 2.2.2. If the existing tests use `TestClient` (sync) instead of `AsyncClient`, adjust the new test to match that style — do not introduce a second transport pattern.

Also note:
- Whether the fixture is module-scoped or function-scoped (affects `monkeypatch` propagation).
- How the existing tests set up `build_research_agent` monkeypatching at the HTTP boundary vs. the router-module level.

- [ ] **Step 2.2.2: Write failing e2e test**

Append to `apps/api/tests/e2e/test_research_endpoint.py`. **Replace `async_client` with whatever the existing fixture is called** (confirmed in Step 2.2.1).

```python
@pytest.mark.e2e
async def test_research_timeout_produces_error_and_stream_end(
    slow_agent_factory,
    monkeypatch,
    async_client,  # ← substitute with actual fixture name from 2.2.1
):
    """DESIGN: Full HTTP path — a slow agent should trigger timeout,
    producing error{reason:timeout} followed by stream_end{source:error}."""
    import app.config.settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "RESEARCH_TIMEOUT_S", 1)
    agent = slow_agent_factory(sleep_s=5)
    monkeypatch.setattr(
        "app.routers.research.build_research_agent",
        lambda **kw: agent,
    )

    events_seen: list[tuple[str, dict]] = []
    async with async_client.stream(
        "POST",
        "/research",
        json={"question": "anything"},
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                event_name = line[len("event: "):].strip()
                events_seen.append((event_name, {}))
            elif line.startswith("data: ") and events_seen:
                events_seen[-1] = (
                    events_seen[-1][0],
                    json.loads(line[len("data: "):]),
                )

    names = [name for name, _ in events_seen]
    assert names[0] == "stream_start"
    assert "error" in names
    assert names[-1] == "stream_end"

    error_data = next(data for name, data in events_seen if name == "error")
    assert error_data["reason"] == "timeout"

    end_data = events_seen[-1][1]
    assert end_data["final_report_source"] == "error"
```

If `async_client` fixture is not present by that name, check `conftest.py` for the equivalent (common names: `client`, `api_client`, `test_client`).

- [ ] **Step 2.2.3: Run — verify PASS (router refactor from Task 2.1 should make this work)**

```bash
cd apps/api && pytest tests/e2e/test_research_endpoint.py -v -k 'timeout' 2>&1 | tail -30
```

Expected: pass. If it fails, diagnose the HTTP layer (sse-starlette emits `event:` and `data:` lines that may need different parsing than shown — adjust the parser to match actual output).

- [ ] **Step 2.2.4: Run the full e2e suite to catch regressions**

```bash
cd apps/api && pytest -m e2e -q 2>&1 | tail -10
```

Expected: all e2e tests pass (including the pre-existing event-sequence smoke).

- [ ] **Step 2.2.5: Commit**

```bash
git add apps/api/tests/e2e/test_research_endpoint.py
git commit -m "$(cat <<'EOF'
test(api): e2e — /research timeout produces error + stream_end

Full ASGI integration test: with RESEARCH_TIMEOUT_S=1 and a slow mock
agent, the HTTP SSE stream contains stream_start → ... → error{reason:
timeout} → stream_end{source:error}. Guards the contract described in
spec §4.4.

Part of Phase 0; refs #2.
EOF
)"
```

### Task 2.3: Chunk 2 verification gate

- [ ] **Step 2.3.1: Run the entire backend test suite**

```bash
cd apps/api && pytest -q 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 2.3.2: Run ruff + mypy across the API app**

```bash
cd apps/api && ruff check . && ruff format --check . && mypy app/
```

Expected: green.

- [ ] **Step 2.3.3: Confirm Chunk 2 git history**

```bash
git log --oneline v1..HEAD
```

Expected: **7 commits total** across Chunks 1–2 — assuming Chunk 1 produced its canonical 5 commits (1 per task × tasks 1.1–1.5). If Chunk 1's commit count was different (e.g., you combined two tasks into one commit), adjust this check accordingly. The invariant is: two new commits since end-of-Chunk-1 (one for router refactor, one for e2e test).

---

## Chunk 3: Frontend contract + reducer

### Task 3.1: Update `SSEEventMap` and add new type aliases

**Files:**
- Modify: `apps/web/lib/types.ts`

- [ ] **Step 3.1.1: Read the current types file**

```bash
cat apps/web/lib/types.ts
```

Confirm the SSEEventMap structure matches what's in spec §4.2.

- [ ] **Step 3.1.2: Apply the three changes**

In `apps/web/lib/types.ts`:

1. Add the two new type aliases near the top (after existing exports):

```typescript
export type ErrorReason = "timeout" | "internal";
export type FinalReportSource = "stream" | "file" | "error";
```

2. In `SSEEventMap`:
   - Remove the line `memory_updated: { namespace: string; key: string };`
   - Replace the `error` line with:
     ```typescript
     error: { message: string; reason: ErrorReason; recoverable: boolean };
     ```
   - Replace `final_report_source?: "stream" | "file";` with:
     ```typescript
     final_report_source?: FinalReportSource;
     ```

- [ ] **Step 3.1.3: Confirm no lingering `memory_updated` references**

```bash
grep -rn "memory_updated" apps/web/ --include="*.ts" --include="*.tsx"
```

Expected: **no output**.

- [ ] **Step 3.1.4: Run the TypeScript compiler (via `next build` dry-run or `tsc --noEmit`)**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | tail -20
```

Expected: no errors. If the reducer still references `"memory_updated"`, that error is expected and will be fixed in Task 3.2.

If there are errors referencing `memory_updated` only in `useResearchStream.ts`, that's fine — tackle in next task.

- [ ] **Step 3.1.5: Commit**

```bash
git add apps/web/lib/types.ts
git commit -m "$(cat <<'EOF'
feat(web): extend SSEEventMap with ErrorReason + FinalReportSource

Adds typed aliases ErrorReason ("timeout" | "internal") and
FinalReportSource ("stream" | "file" | "error"). Extends the error
event payload to carry reason + recoverable. Removes orphan
memory_updated slot. Matches api-side changes from Chunk 1.

Reducer update follows in the next commit.

Part of Phase 0; refs #2.
EOF
)"
```

### Task 3.2: Update `useResearchStream` state shape + reducer

**Files:**
- Modify: `apps/web/lib/useResearchStream.ts`
- Test: `apps/web/lib/useResearchStream.test.ts` (create if absent)

- [ ] **Step 3.2.1: Preconditions check — existing test file + exported symbols**

```bash
ls apps/web/lib/useResearchStream.test.ts 2>&1 || echo "NOT_FOUND"
grep -n "^export" apps/web/lib/useResearchStream.ts
```

- If the test file is absent, plan to create it. Reuse any existing vitest setup patterns from other `apps/web/**/*.test.ts(x)` files.
- The second grep must show that `reducer` and `initial` are **named exports** of `useResearchStream.ts`. If they are not (for example, if `reducer` is only used locally inside the `useResearchStream` hook), you must add `export` in front of those declarations in Step 3.2.6 — or the test imports will fail.

- [ ] **Step 3.2.2: Write failing test — error event stores reason + recoverable**

Create or append to `apps/web/lib/useResearchStream.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { reducer, initial } from "./useResearchStream";
import type { SSEFrame } from "./sseParser";

describe("useResearchStream reducer — error event", () => {
  it("stores reason and recoverable when error event arrives", () => {
    const frame: SSEFrame = {
      event: "error",
      data: {
        message: "Research timed out. Please try again.",
        reason: "timeout",
        recoverable: true,
      },
    };
    const next = reducer(initial, frame);
    expect(next.status).toBe("error");
    expect(next.error).toBe("Research timed out. Please try again.");
    expect(next.errorReason).toBe("timeout");
    expect(next.errorRecoverable).toBe(true);
  });
});
```

- [ ] **Step 3.2.3: Write failing test — SPECIFICATION ANCHOR (stream_end after error preserves status)**

Append:

```typescript
describe("useResearchStream reducer — stream_end after error", () => {
  it("preserves status:'error' when stream_end arrives with source='error'", () => {
    // DESIGN: Per spec §4.3, stream_end with final_report_source:"error"
    // must be a no-op beyond reflecting source — the preceding error event
    // already set status:"error". Removing this branch breaks the contract
    // guarantee in spec §4.4.
    const afterError = reducer(initial, {
      event: "error",
      data: { message: "boom", reason: "internal", recoverable: false },
    } as SSEFrame);

    const afterEnd = reducer(afterError, {
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
    expect(afterEnd.error).toBe("boom");
    // todos/files/subagents unchanged
    expect(afterEnd.todos).toEqual(afterError.todos);
    expect(afterEnd.files).toEqual(afterError.files);
    expect(afterEnd.subagents).toEqual(afterError.subagents);
  });
});
```

- [ ] **Step 3.2.4: Write failing test — success path `stream_end` still transitions to done**

Append:

```typescript
describe("useResearchStream reducer — stream_end success path", () => {
  it("transitions to done and finalizes todos when source='stream'", () => {
    const withTodos = reducer(initial, {
      event: "todo_updated",
      data: { items: [{ content: "one", status: "in_progress" }] },
    } as SSEFrame);

    const afterEnd = reducer(withTodos, {
      event: "stream_end",
      data: {
        final_report: "THE REPORT",
        usage: {},
        versions_used: {},
        final_report_source: "stream",
      },
    } as SSEFrame);

    expect(afterEnd.status).toBe("done");
    expect(afterEnd.report).toBe("THE REPORT");
    expect(afterEnd.reportSource).toBe("stream");
    expect(afterEnd.todos[0].status).toBe("completed");
  });

  it("reflects source='file' when fallback draft was used", () => {
    const afterEnd = reducer(initial, {
      event: "stream_end",
      data: {
        final_report: "FROM DRAFT",
        usage: {},
        versions_used: {},
        final_report_source: "file",
      },
    } as SSEFrame);

    expect(afterEnd.status).toBe("done");
    expect(afterEnd.reportSource).toBe("file");
  });
});
```

- [ ] **Step 3.2.5: Run — verify FAILS**

```bash
cd apps/web && npm test -- useResearchStream.test 2>&1 | tail -20
```

Expected: multiple failures (`errorReason` doesn't exist on state; reducer doesn't handle `final_report_source === "error"` branch yet).

- [ ] **Step 3.2.6: Apply the reducer + state changes**

In `apps/web/lib/useResearchStream.ts`:

1. Import the new types at the top:

```typescript
import { TodoItem, FileRef, SubagentRun, CompressionEvent, Reflection, ErrorReason } from "./types";
```

2. Widen `ReportSource`:

```typescript
export type ReportSource = "stream" | "file" | "error";
```

3. Extend `ResearchState`:

```typescript
export type ResearchState = {
  todos: TodoItem[];
  files: FileRef[];
  subagents: Record<string, SubagentRun>;
  compressions: CompressionEvent[];
  reflections: Reflection[];
  report: string;
  reportSource: ReportSource | null;
  status: "idle" | "loading" | "streaming" | "done" | "error";
  question?: string;
  error?: string;
  errorReason?: ErrorReason;
  errorRecoverable?: boolean;
};
```

4. Update the `"error"` case in the reducer:

```typescript
case "error":
  return {
    ...state,
    status:            "error",
    error:             data.message,
    errorReason:       data.reason,
    errorRecoverable:  data.recoverable,
  };
```

5. Update the `"stream_end"` case to add the no-op branch at the top:

```typescript
case "stream_end":
  // Error path: `error` event already set status:"error". stream_end is
  // just the terminal signal — freeze partial state, do NOT flip to "done",
  // do NOT force-complete todos.
  //
  // DESIGN: see docs/superpowers/specs/2026-04-24-phase-0-stabilize-sse-contract-design.md §4.3
  if (data.final_report_source === "error") {
    // status is already "error" (set by the preceding error event);
    // this branch is intentionally a no-op beyond reflecting
    // source="error" in state. Do NOT set status here.
    return { ...state, reportSource: "error" };
  }
  return {
    ...state,
    status: "done",
    report: data.final_report || state.report,
    reportSource: data.final_report
      ? ((data.final_report_source as ReportSource | undefined) ?? "stream")
      : (state.reportSource ?? "stream"),
    todos: state.todos.map((t) =>
      t.status !== "completed" ? { ...t, status: "completed" as const } : t,
    ),
  };
```

- [ ] **Step 3.2.7: Run tests — verify PASS**

```bash
cd apps/web && npm test -- useResearchStream.test 2>&1 | tail -20
```

Expected: all 4 new tests pass.

- [ ] **Step 3.2.8: Run the full frontend test suite + lint + type-check**

```bash
cd apps/web && npm test -- --run 2>&1 | tail -10 && npm run lint && npx tsc --noEmit
```

Expected: all green.

- [ ] **Step 3.2.9: Verify `next build` succeeds (catches TS regressions in unreferenced paths)**

```bash
cd apps/web && npm run build 2>&1 | tail -20
```

Expected: build completes without errors.

- [ ] **Step 3.2.10: Commit**

```bash
git add apps/web/lib/useResearchStream.ts apps/web/lib/useResearchStream.test.ts
git commit -m "$(cat <<'EOF'
feat(web): reducer preserves status on stream_end with source="error"

Adds errorReason + errorRecoverable fields to ResearchState, populated
from the extended error event. The stream_end reducer gains a no-op
branch when final_report_source === "error" — the preceding error
event has already set status:"error", so stream_end is just the
terminal signal.

Test suite includes the SPECIFICATION ANCHOR (spec §4.3) that codifies
the "error is the status-transition, stream_end is the terminal signal"
contract.

Part of Phase 0; refs #2.
EOF
)"
```

### Task 3.3: Chunk 3 verification gate

- [ ] **Step 3.3.1: Full frontend test + build**

```bash
cd apps/web && npm test -- --run && npm run lint && npm run format:check && npm run build
```

Expected: all green.

- [ ] **Step 3.3.2: Confirm no lingering `memory_updated` anywhere in the repo**

```bash
grep -rn "memory_updated" apps/ --include="*.py" --include="*.ts" --include="*.tsx"
```

Expected: **no output**.

- [ ] **Step 3.3.3: Git history**

```bash
git log --oneline v1..HEAD
```

Expected: 9 commits total (5 Chunk 1 + 2 Chunk 2 + 2 Chunk 3).

---

## Chunk 4: Documentation, smoke, and pull request

### Task 4.1: Add `/CHANGELOG.md`

**Files:**
- Create: `/CHANGELOG.md`

- [ ] **Step 4.1.1: Create the file**

Create `/CHANGELOG.md` at the repo root with this exact content:

```markdown
# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project uses an `[Unreleased]` section at the top where entries
accrue between releases. Each PR that changes user-visible behavior
updates this file; entries graduate to a dated version header when a
release is cut.

## [Unreleased]

### Added
- `RESEARCH_TIMEOUT_S` setting (default 500s, bounded 10–3600) enforced around
  agent streaming via `asyncio.timeout`.
- `reason` field on the `error` SSE event with values `"timeout" | "internal"`.
- `"error"` variant on `stream_end.final_report_source`.
- This `CHANGELOG.md` file and its convention (documented in `CONTRIBUTING.md`).

### Changed
- `error` SSE event now carries sanitized per-reason messages from a static
  catalog; raw exception strings are logged server-side only. `recoverable`
  flag derives from `reason` (`"timeout" → true`, `"internal" → false`).
- `/research` now emits `stream_end` unconditionally via a `finally` block —
  a failed run no longer leaves the frontend reducer stuck in `"streaming"`.

### Removed
- Orphan `memory_updated` SSE event — factory function, `SSEEventMap` entry,
  and type unused across both api and web. Future semantic-memory features
  will introduce a mem0-native `memory_operation` event (see
  `reseachers/deep-agents-harness-upgrade-milestones.md` §10 parking lot).

### Fixed
- Missing `stream_end` on mid-stream exceptions (`stream_end` is now
  guaranteed on every terminal path).
- Unbounded `/research` runtime — long hangs now fail fast at the timeout.
```

### Task 4.2: Add Changelog section to `/CONTRIBUTING.md`

**Files:**
- Modify: `/CONTRIBUTING.md`

- [ ] **Step 4.2.1: Read the existing file and find the insertion point**

```bash
grep -n "^## " CONTRIBUTING.md
```

Confirm there are `## Commit Convention` and `## Branch Naming` sections. Insert the new Changelog section between them (after Commit Convention ends, before Branch Naming begins).

- [ ] **Step 4.2.2: Add the new section**

Insert this block between `## Commit Convention` and `## Branch Naming`:

```markdown
## Changelog

Every PR that changes user-visible behavior updates `/CHANGELOG.md`'s
`[Unreleased]` section. Use the [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
subhead convention:

- **Added** — new features, new events, new settings, new files.
- **Changed** — existing behavior changed in a backward-incompatible or
  observable way.
- **Deprecated** — features marked for removal in a future release.
- **Removed** — features removed in this change.
- **Fixed** — bug fixes.
- **Security** — vulnerability fixes.

Pure internal refactors (no user-visible or operator-visible effect) can
skip the changelog. When in doubt, add an entry — it's cheap.

When a release is cut, rename `## [Unreleased]` to `## [x.y.z] - YYYY-MM-DD`,
and start a new empty `## [Unreleased]` section above it.
```

### Task 4.3: Add `RESEARCH_TIMEOUT_S` to `.env.example`

**Files:**
- Modify: `apps/api/.env.example`

- [ ] **Step 4.3.1: Insert the new line**

In `apps/api/.env.example`, between line 12 (`COMPRESSION_DETECTION_RATIO=0.7`) and line 13 (`CORS_ORIGINS=...`), insert:

```bash
# Research endpoint timeout in seconds (10-3600, default 500)
RESEARCH_TIMEOUT_S=500
```

The resulting operational-tunables block should read:

```bash
CHECKPOINT_DB_PATH=./data/checkpoints.sqlite
VFS_OFFLOAD_THRESHOLD_TOKENS=20000
COMPRESSION_DETECTION_RATIO=0.7
# Research endpoint timeout in seconds (10-3600, default 500)
RESEARCH_TIMEOUT_S=500
CORS_ORIGINS=["http://localhost:3000"]
```

### Task 4.4: Commit the documentation triplet

- [ ] **Step 4.4.1: Stage and commit**

```bash
git add CHANGELOG.md CONTRIBUTING.md apps/api/.env.example
git commit -m "$(cat <<'EOF'
docs: add CHANGELOG.md, CONTRIBUTING changelog section, env example entry

- /CHANGELOG.md seeded with [Unreleased] block populated from this PR's
  changes (Added/Changed/Removed/Fixed per Keep a Changelog 1.1.0).
- /CONTRIBUTING.md adds a "Changelog" section between Commit Convention
  and Branch Naming documenting the [Unreleased] convention.
- apps/api/.env.example adds the RESEARCH_TIMEOUT_S=500 line with a
  brief comment noting the bounds.

Part of Phase 0; refs #2.
EOF
)"
```

### Task 4.5: Manual smoke verification

**Files:** none (runtime smoke only)

- [ ] **Step 4.5.1: Start backend + frontend in two shells**

Shell A:
```bash
cd apps/api && uvicorn app.main:app --reload --port 8000
```

Shell B:
```bash
cd apps/web && npm run dev
```

Confirm both start without errors. Backend should log `[RESEARCH] Settings validated` or equivalent fail-fast pass; frontend should serve `http://localhost:3000`.

- [ ] **Step 4.5.2: Happy-path smoke**

In the browser at `http://localhost:3000/research`, submit a short research question ("What is a Python generator?"). Expected:
- SSE stream proceeds normally.
- Final UI state: `status: "done"`, report visible, no error banner.
- Terminal (backend) shows `[RESEARCH] Stream complete … source=stream`.

- [ ] **Step 4.5.3: Timeout smoke**

Stop the backend. Temporarily set in `apps/api/.env`:

```bash
RESEARCH_TIMEOUT_S=5
```

Restart backend (`uvicorn app.main:app --reload --port 8000`). In the browser, submit a question that will take longer than 5 s ("Compare five different machine learning algorithms with examples and code"). Expected:
- SSE stream stops around the 5 s mark.
- UI shows the `"Research timed out."` message with status stuck at `"error"`.
- UI is **not** stuck in `"streaming"` state (this is the bug Phase 0 fixes).
- Backend terminal shows `[RESEARCH] Timeout after 5s`.

Restore `RESEARCH_TIMEOUT_S=500` (or remove the override) and restart the backend.

- [ ] **Step 4.5.4: No `memory_updated` in terminal output**

In both backend and frontend terminals, confirm the string `memory_updated` never appears in the normal stream of logs for any successful run. Nothing to grep — just visually verify.

- [ ] **Step 4.5.5: Record the smoke results**

Capture both shell terminals (or screenshots of UI) — these go in the PR body as evidence.

### Task 4.6: Open the PR

**Files:** none (git + gh operations)

- [ ] **Step 4.6.1: Push the branch**

```bash
git push -u github fix/phase-0-stabilize-sse-contract
```

If your remote is named `origin` (or another name) rather than `github` — per the preflight check in Step 0.1.1 — substitute accordingly:

```bash
git push -u <your-remote-name> fix/phase-0-stabilize-sse-contract
```

- [ ] **Step 4.6.2: Open the PR with the review checklist in the body**

```bash
gh pr create \
  --base v1 \
  --head fix/phase-0-stabilize-sse-contract \
  --title "fix(api,web): stabilize SSE contract + timeout + remove memory_updated" \
  --body "$(cat <<'EOF'
## Summary

Phase 0 of the Deep Agents Harness Upgrade. Closes the three latent SSE
contract bugs that block downstream phases:

1. `stream_end` now emitted on every terminal path (success, timeout,
   unhandled exception) via a `finally` block.
2. `RESEARCH_TIMEOUT_S` (default 500 s, bounds 10–3600) enforces an upper
   bound on agent runs via `asyncio.timeout`.
3. Orphan `memory_updated` SSE event removed (had zero emitters and
   zero reducer handlers).

Plus the cross-cutting addition of `/CHANGELOG.md` with the Keep a
Changelog 1.1.0 `[Unreleased]` convention, documented in
`CONTRIBUTING.md`.

## Design

Spec: `docs/superpowers/specs/2026-04-24-phase-0-stabilize-sse-contract-design.md`
Plan: `docs/superpowers/plans/2026-04-24-phase-0-implementation-plan.md`

## Test Plan

- [ ] Backend unit tests pass (`cd apps/api && pytest -m unit`)
- [ ] Backend e2e tests pass (`cd apps/api && pytest -m e2e`)
- [ ] Frontend tests pass (`cd apps/web && npm test -- --run`)
- [ ] Linters clean (`ruff check . && mypy app/` in apps/api; `npm run lint && npm run format:check` in apps/web)
- [ ] `next build` succeeds (`cd apps/web && npm run build`)
- [ ] Manual smoke per plan §4.5 performed and recorded below
- [ ] `grep -rn memory_updated apps/` returns 0 results

## Manual smoke results

<paste terminal captures from §4.5.2, §4.5.3, §4.5.4>

## Reviewer Checklist

- [ ] Contract changes match spec §4
- [ ] `grep -r memory_updated` returns 0 results across the repo
- [ ] `RESEARCH_TIMEOUT_S` validation bounds (10–3600) present
- [ ] Router generator has `try/except/finally` with `stream_end` in `finally`
- [ ] `error` factory takes only `reason`; message from catalog
- [ ] No `str(e)` sent to client — only logged
- [ ] Reducer `stream_end` has `if final_report_source === "error"` early return
- [ ] `CHANGELOG.md` populated with six bullets from spec §7.1
- [ ] `CONTRIBUTING.md` has new Changelog section in right place
- [ ] `.env.example` has `RESEARCH_TIMEOUT_S=500` line
- [ ] Existing 27 chunk_mapper tests pass unchanged
- [ ] Existing e2e event-sequence tests pass unchanged

Closes #2
EOF
)"
```

- [ ] **Step 4.6.3: Confirm the PR landed on the milestone**

```bash
gh pr view --json url,milestone,labels --jq '{url, milestone: .milestone.title, labels: .labels | map(.name)}'
```

Expected: PR URL printed; milestone is `"Deep Agents Harness Upgrade — Hybrid Path"` (via the `Closes #2` footer auto-inheriting). If the milestone isn't auto-attached, manually add it:

```bash
gh pr edit --milestone "Deep Agents Harness Upgrade — Hybrid Path"
```

### Task 4.7: Final verification and handoff

- [ ] **Step 4.7.1: Confirm CI is green on the PR**

```bash
gh pr checks --watch
```

Expected: all checks pass.

- [ ] **Step 4.7.2: Post the smoke evidence as a PR comment (if not already in the body)**

```bash
gh pr comment --body "Manual smoke per plan §4.5:
- Happy path: ✅ completed in ~30 s, source=stream
- Timeout: ✅ 5 s timeout triggered, UI correctly stayed in 'error' state
- No memory_updated events observed"
```

- [ ] **Step 4.7.3: Hand off to the reviewer**

At this point the PR is reviewable. Do not merge until:
- All CI checks green
- Reviewer checklist in PR body fully ticked
- At least one human review approves

### Task 4.8: Chunk 4 + overall verification

- [ ] **Step 4.8.1: Count commits on the branch**

```bash
git log --oneline v1..HEAD | wc -l
```

Expected: **10 commits** (5 Chunk 1 + 2 Chunk 2 + 2 Chunk 3 + 1 Chunk 4).

- [ ] **Step 4.8.2: Confirm the branch is clean (nothing staged, nothing unstaged)**

```bash
git status
```

Expected: `nothing to commit, working tree clean`.

- [ ] **Step 4.8.3: Final end-to-end test sweep (one more time before signing off)**

```bash
cd apps/api && pytest -q && ruff check . && mypy app/
cd ../web && npm test -- --run && npm run lint && npm run build
```

Expected: all green.

---

## Appendix A: Rollback procedure

If this PR needs to be reverted post-merge:

```bash
git checkout v1 && git pull github v1
git revert <merge-commit-sha> --no-edit
git push github v1
```

No migrations, no env-var renames, no DB changes — the revert is side-effect free (per spec §10). Confirm post-revert via one happy-path smoke run.

## Appendix B: Quick sanity grep cheatsheet

Commands the reviewer will run. Make sure your final diff passes them:

```bash
# All three expectations MUST be empty or match
grep -rn "memory_updated" apps/ --include="*.py" --include="*.ts" --include="*.tsx"     # → 0 hits
grep -n "asyncio.timeout" apps/api/app/routers/research.py                              # → 1 hit
grep -n "RESEARCH_TIMEOUT_S" apps/api/app/config/settings.py apps/api/.env.example      # → 2 hits (1 per file)
grep -n "ERROR_MESSAGES" apps/api/app/streaming/events.py                               # → ≥2 hits
grep -n 'final_report_source === "error"' apps/web/lib/useResearchStream.ts             # → 1 hit
```

## Appendix C: Pre-existing invariants this plan does NOT touch

- `ChunkMapper` in `apps/api/app/streaming/chunk_mapper.py` and its 27 unit tests.
- `draft.md` fallback logic for streamed reports < 200 chars.
- Deep Agents subagent composition (`agent_factory.py`) — supervisor migration is Phase 3a.
- Prompt registry and versioning.
- Frontend SSE parser (`lib/sseParser.ts`).
- CORS middleware, settings bootstrapping, lifespan hooks.

If any of these break during implementation, **stop and investigate** — Phase 0 should not cause collateral damage.
