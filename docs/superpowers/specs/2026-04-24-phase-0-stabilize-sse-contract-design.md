# Design Spec — Phase 0: Stabilize SSE Contract + Timeout

| | |
| :--- | :--- |
| **Date** | 2026-04-24 |
| **Status** | Approved (design) — pending implementation |
| **Author** | Minh Tran (via brainstorming with Claude) |
| **GitHub** | [Issue #2](https://github.com/minhtran3124/chat-agents/issues/2) · [Milestone #1 "Deep Agents Harness Upgrade — Hybrid Path"](https://github.com/minhtran3124/chat-agents/milestone/1) |
| **Related docs** | [`reseachers/deep-agents-harness-upgrade-roadmap.md`](../../../reseachers/deep-agents-harness-upgrade-roadmap.md) · [`reseachers/deep-agents-harness-upgrade-milestones.md`](../../../reseachers/deep-agents-harness-upgrade-milestones.md) |
| **Phase** | 0 of 6 in the Deep Agents Harness Upgrade hybrid path |
| **Scope estimate** | ~170 LOC across ~8 files; ~19 new/amended tests; 0.5–1 focused day |

---

## 1. Goal

Close three latent bugs in the SSE streaming contract so the foundation is consistent before Phase 1+ adds observability, guardrails, HITL, and beyond. The bugs are:

1. **Missing `stream_end` on error paths** — when `/research` raises mid-stream, the backend emits an `error` event and exits without `stream_end`. The frontend reducer can end up in inconsistent terminal states.
2. **Orphan `memory_updated` SSE event** — declared in `SSEEventMap` and `events.py` but never emitted by the backend and never handled in the frontend reducer. Dead weight on the contract surface.
3. **No timeout on `/research`** — a hung Tavily call or stuck LLM request ties up the FastAPI process indefinitely.

Plus one cross-cutting improvement:

4. **Introduce `CHANGELOG.md`** — every subsequent phase will contribute release-note-grade entries; starting the discipline now is cheap and compounds.

## 2. Scope

### 2.1 In scope

- Router: `try/except/finally` restructure; `asyncio.timeout(RESEARCH_TIMEOUT_S)` wrapping the whole generator body; unconditional `stream_end` emission in `finally`.
- SSE contract:
  - `error` event gains a `reason: "timeout" | "internal"` enum; `message` becomes a sanitized static catalog string; `recoverable` derived from `reason`.
  - `stream_end.final_report_source` Literal extends to include `"error"`.
  - `memory_updated` removed end-to-end (factory, type, reducer slot if any).
- Settings: new `RESEARCH_TIMEOUT_S: int = 500` with bounds (10–3600) validated by pydantic `Field`.
- Frontend reducer: preserves `status: "error"` when `stream_end` arrives with `final_report_source === "error"`; stores new `errorReason` and `errorRecoverable` fields on state.
- `CHANGELOG.md` created at repo root with Keep a Changelog 1.1.0 format; initial `[Unreleased]` section populated from this PR's changes.
- `CONTRIBUTING.md`: new "Changelog" section between "Commit Convention" and "Branch Naming".
- `apps/api/.env.example`: new `RESEARCH_TIMEOUT_S=500` line near existing operational tunables.
- Tests: ~14 backend + ~5 frontend.

### 2.2 Out of scope

- Auth, rate limiting — Phase 6.
- Structured logging (structlog), LangSmith tracing, Prometheus metrics — Phase 1.
- Guardrails — Phase 2a.
- HITL `interrupt()` / approval flow — Phase 2b.
- Supervisor migration, MCP client — Phase 3.
- Sandboxed code execution — Phase 4.
- Eval framework — Phase 5.
- `deepagents` version bump — already at 0.5.2 in `apps/api/pyproject.toml:8`; verification = existing test suite passing.
- `chunk_mapper.py` changes — not touched; existing 27 unit tests are the regression canary.
- Semantic memory (mem0 / pgvector) — deferred; future `memory_operation` event will replace the `memory_updated` slot when semantic memory lands (see milestones §10 parking lot).
- Version bump in `pyproject.toml` — changelog uses `[Unreleased]` pattern; actual version bump happens only when a real release is cut.
- Per-request timeout override in `ResearchRequest` — YAGNI; server-level env var is sufficient.

## 3. Design decisions summary

| # | Decision | Value |
| :-: | :--- | :--- |
| D1 | `memory_updated` — emit or remove? | **Remove** (orphan on both sides; shape won't match mem0 anyway) |
| D2 | `error` and `stream_end` composition on failure | **Both events**, error first, stream_end in `finally` |
| D3 | `reason` field shape | **Enum**: `"timeout" \| "internal"` |
| D4 | Timeout default | **500 s** |
| D5 | Per-request timeout override | **No** |
| D6 | Timeout wraps what? | **Whole generator body** (astream + aget_state + fallback logic) |
| D7 | Error message content | **Static per-reason catalog** (never `str(e)`); raw exception goes only to logs |
| D8 | `recoverable` flag derivation | **From `reason`**: `"timeout" → true`, `"internal" → false` |
| D9 | `final_report` on failure | **Empty string** (state from preceding text_delta events already preserved in frontend `state.report`) |
| D10 | PR strategy | **Single PR** per milestone doc; squash-merge |
| D11 | CHANGELOG location & format | **Repo-root `/CHANGELOG.md`**; Keep a Changelog 1.1.0 with `[Unreleased]` section |

## 4. Contract changes

### 4.1 `apps/api/app/streaming/events.py`

```python
# New type aliases (exported)
ErrorReason = Literal["timeout", "internal"]
FinalReportSource = Literal["stream", "file", "error"]

# New constant
ERROR_MESSAGES: dict[ErrorReason, str] = {
    "timeout":  "Research timed out. Please try again with a simpler "
                "question or contact support if this persists.",
    "internal": "Research failed due to an internal error. Please try "
                "again shortly.",
}

# memory_updated factory: REMOVED

# error factory: CHANGED signature
def error(reason: ErrorReason) -> dict:
    return _sse("error", {
        "message":     ERROR_MESSAGES[reason],
        "reason":      reason,
        "recoverable": reason == "timeout",
    })

# stream_end factory: type widened
def stream_end(
    final_report: str,
    usage: dict[str, Any],
    versions_used: dict[str, str],
    final_report_source: FinalReportSource = "stream",  # was Literal["stream", "file"]
) -> dict:
    ...  # body unchanged
```

**Breaking change note**: `error()` factory signature changed from `error(message: str, recoverable: bool = False)` to `error(reason: ErrorReason)`. The only caller is `apps/api/app/routers/research.py`, which is refactored in §5.

### 4.2 `apps/web/lib/types.ts`

```typescript
// New exports
export type ErrorReason = "timeout" | "internal";
export type FinalReportSource = "stream" | "file" | "error";

// SSEEventMap changes
export type SSEEventMap = {
  // ... unchanged events omitted ...

  // REMOVED: memory_updated: { namespace: string; key: string };

  // EXTENDED:
  error: { message: string; reason: ErrorReason; recoverable: boolean };

  // EXTENDED:
  stream_end: {
    final_report: string;
    usage: Record<string, unknown>;
    versions_used: Record<string, string>;
    final_report_source?: FinalReportSource;
  };
};
```

### 4.3 `apps/web/lib/useResearchStream.ts`

```typescript
// Widened ReportSource
export type ReportSource = "stream" | "file" | "error";

// Extended ResearchState
export type ResearchState = {
  // ... unchanged fields omitted ...
  error?: string;
  errorReason?: ErrorReason;
  errorRecoverable?: boolean;
};

// Reducer changes (two cases):
case "error":
  return {
    ...state,
    status:            "error",
    error:             data.message,
    errorReason:       data.reason,
    errorRecoverable:  data.recoverable,
  };

case "stream_end":
  // Error path: `error` event already set status:"error". stream_end is
  // just the terminal signal — freeze partial state, do NOT flip to "done",
  // do NOT force-complete todos.
  //
  // DESIGN: see docs/superpowers/specs/2026-04-24-phase-0-stabilize-sse-contract-design.md §4.3
  if (data.final_report_source === "error") {
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

### 4.4 Event emission matrix

| Outcome | Events emitted (order) | `final_report_source` | Frontend `status` after |
| :--- | :--- | :-: | :-: |
| Success — streamed report ≥ 200 chars | `stream_start` → … → `stream_end` | `"stream"` | `"done"` |
| Success — streamed < 200 chars, `draft.md` present | `stream_start` → … → `stream_end` | `"file"` | `"done"` |
| Timeout (exceeds `RESEARCH_TIMEOUT_S`) | `stream_start` → … → `error{reason:"timeout"}` → `stream_end` | `"error"` | `"error"` |
| Any unhandled exception | `stream_start` → … → `error{reason:"internal"}` → `stream_end` | `"error"` | `"error"` |

**Invariants the contract now guarantees:**

1. Every `/research` request emits exactly one `stream_start` and exactly one `stream_end`.
2. If a run fails, exactly one `error` event is emitted, arriving before `stream_end`.
3. `stream_end.final_report_source === "error"` is the canonical "this run failed" signal.
4. No run exceeds `RESEARCH_TIMEOUT_S`. Hard guarantee via `asyncio.timeout`.
5. No exception details leak to the client. Every message is one of two catalog strings.

## 5. Router refactor — `apps/api/app/routers/research.py`

### 5.1 Target generator body

```python
async def generator() -> AsyncGenerator[dict, None]:
    logger.info(
        "[RESEARCH] Agent invoked thread_id=%s prompt_versions=%s question=%r",
        thread_id, versions_used, payload.question[:120],
    )
    yield events.stream_start(thread_id)

    # Terminal accumulators — populated on success, overwritten on failure
    final_report: str = ""
    final_report_source: FinalReportSource = "error"
    usage: dict = {}
    error_reason: ErrorReason | None = None

    try:
        async with asyncio.timeout(settings.RESEARCH_TIMEOUT_S):
            async for mode, chunk in agent.astream(
                {"messages": [{"role": "user", "content": payload.question}]},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode=["values", "messages", "updates"],
            ):
                async for ev in mapper.process(mode, chunk):
                    if ev["event"] == "text_delta":
                        final_report_parts.append(json.loads(ev["data"])["content"])
                    yield ev

            if (
                not mapper.saw_compression
                and mapper.peak_tokens > SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS
            ):
                yield events.compression_triggered(
                    original_tokens=mapper.peak_tokens,
                    compressed_tokens=mapper.peak_tokens // 2,
                    synthetic=True,
                )

            try:
                final_state = await agent.aget_state(
                    {"configurable": {"thread_id": thread_id}}
                )
                usage = final_state.values.get("usage", {}) if final_state else {}
                files = final_state.values.get("files", {}) if final_state else {}
            except Exception:
                usage = {}
                files = {}

            streamed_report = "".join(final_report_parts)
            final_report = streamed_report
            final_report_source = "stream"

            draft = files.get(FALLBACK_DRAFT_FILENAME)
            if (
                len(streamed_report) < MIN_STREAM_REPORT_CHARS
                and isinstance(draft, str)
                and len(draft) >= MIN_STREAM_REPORT_CHARS
            ):
                logger.warning(
                    "[RESEARCH] Final-report fallback triggered — streamed only %d "
                    "chars; using %s (%d chars). Prompt compliance issue worth "
                    "investigating (main prompt version=%s).",
                    len(streamed_report), FALLBACK_DRAFT_FILENAME, len(draft),
                    versions_used.get("main"),
                )
                final_report = draft
                final_report_source = "file"

    except asyncio.TimeoutError:
        error_reason = "timeout"
        final_report = ""
        final_report_source = "error"
        logger.error(
            "[RESEARCH] Timeout after %ds thread_id=%s",
            settings.RESEARCH_TIMEOUT_S, thread_id,
        )

    except Exception:
        error_reason = "internal"
        final_report = ""
        final_report_source = "error"
        logger.error(
            "[RESEARCH] Stream error — agent run abandoned:\n%s",
            traceback.format_exc(),
        )

    finally:
        # Emit error BEFORE stream_end so the reducer's status transition
        # runs before stream_end's no-op branch (see useResearchStream).
        if error_reason is not None:
            yield events.error(error_reason)

        logger.info(
            "[RESEARCH] Stream complete thread_id=%s report_chars=%d source=%s "
            "error_reason=%s nodes_seen=%s prompt_versions=%s usage=%s",
            thread_id, len(final_report), final_report_source,
            error_reason, sorted(mapper.seen_nodes), versions_used, usage,
        )
        yield events.stream_end(
            final_report=final_report,
            usage=usage,
            versions_used=versions_used,
            final_report_source=final_report_source,
        )
```

### 5.2 Design rationale (per-decision)

| Decision | Rationale |
| :--- | :--- |
| `stream_start` outside the `try` block | Clients must always see `stream_start` to open their reducer; it is the first observable of any valid HTTP 200 response. |
| `asyncio.timeout` inside the `try`, wrapping astream + post-stream logic | Timeout covers everything except the initial `stream_start` emit (D6). |
| Two distinct `except` branches | `asyncio.TimeoutError` → `"timeout"`; everything else → `"internal"`. Keeps categorization explicit. |
| `error_reason` flag pattern with single `finally` emission | Keeps `finally` block simple and linear; event emission order is deterministic: `error` (if set) → `stream_end`. |
| Inner `aget_state` try/except preserved | State fetch failures are non-critical — `usage={}` in stream_end is acceptable, not worth escalating to `"internal"`. |
| `final_report_source` defaults to `"error"` | Belt-and-suspenders: if any exception slips past both except branches (shouldn't happen), `stream_end` still signals failure accurately. |
| Timeout branch does NOT log `traceback.format_exc()` | Timeouts have no meaningful stack trace — the exception is raised at an arbitrary point by the runtime. Log the duration + thread instead. |

### 5.3 Non-changes (surgical discipline)

- Constants `SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS`, `MIN_STREAM_REPORT_CHARS`, `FALLBACK_DRAFT_FILENAME` — unchanged.
- `ChunkMapper` — not touched; its 27 unit tests validate regressions.
- `agent.astream(...)` call shape — unchanged.
- `draft.md` fallback logic on success path — unchanged.
- Request validation (`HTTPException` on prompt version KeyError) — unchanged.
- Router prefix, tags, path — unchanged.

### 5.4 Why `yield` inside `finally` is correct for async generators

Python's async generator protocol runs the body on every `__anext__()` call. During normal exception flow (timeout, internal), the `except` clauses run, then `finally` runs *while the generator is still alive*. Yields inside `finally` are genuinely delivered to `sse-starlette` and flushed to the client. The only case where `finally` won't yield successfully is if the client has already disconnected — in which case `sse-starlette` raises `asyncio.CancelledError` on the next yield, which is a non-issue because the connection is already gone. This is why `try/except/finally` + `yield in finally` is the correct idiom for "always emit terminal event" in SSE generators, superior to decorators or context managers for this use case.

## 6. Settings change — `apps/api/app/config/settings.py`

```python
RESEARCH_TIMEOUT_S: int = Field(
    default=500,
    ge=10,
    le=3600,
    description="Maximum wall-clock seconds for a single /research run "
                "before asyncio.timeout cancels it and emits a timeout error.",
)
```

**Bounds rationale:**

- `ge=10` — prevents `RESEARCH_TIMEOUT_S=0` or very small values that would kill every legitimate run before the first LLM token arrives.
- `le=3600` — prevents misconfiguration where a stuck Tavily connection ties up a FastAPI worker for hours; forces explicit operator intent for long timeouts.

Validation error at startup is fail-fast, matching the repo's existing pattern (e.g., `_resolve_and_validate` fail-fasts on missing API keys).

## 7. `CHANGELOG.md` + `CONTRIBUTING.md` + `.env.example`

### 7.1 New file: `/CHANGELOG.md`

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

### 7.2 `/CONTRIBUTING.md` — new section

Inserted between "Commit Convention" and "Branch Naming":

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

### 7.3 `/apps/api/.env.example` — new line

Place near the other operational tunables (`VFS_OFFLOAD_THRESHOLD_TOKENS`, `COMPRESSION_DETECTION_RATIO`):

```bash
# Research endpoint timeout in seconds (10-3600, default 500)
RESEARCH_TIMEOUT_S=500
```

## 8. Test plan

### 8.1 Backend tests (pytest)

| # | File | Kind | Test |
| :-: | :--- | :-: | :--- |
| T1 | `tests/unit/test_events.py` | NEW | `events.error("timeout")` returns `{message: ERROR_MESSAGES["timeout"], reason: "timeout", recoverable: True}` |
| T2 | `tests/unit/test_events.py` | NEW | `events.error("internal")` returns `{..., reason: "internal", recoverable: False}` |
| T3 | `tests/unit/test_events.py` | NEW | `events.stream_end(..., final_report_source="error")` serializes correctly |
| T4 | `tests/unit/test_events.py` | AMEND | Remove any lingering test for `events.memory_updated`; absence of import is the check |
| T5 | `tests/unit/test_settings.py` | NEW | `Settings(RESEARCH_TIMEOUT_S=5)` raises `ValidationError` |
| T6 | `tests/unit/test_settings.py` | NEW | `Settings(RESEARCH_TIMEOUT_S=7200)` raises `ValidationError` |
| T7 | `tests/unit/test_settings.py` | NEW | `Settings(RESEARCH_TIMEOUT_S=500)` accepted |
| T8 | `tests/unit/test_research_router.py` | NEW | Generator with `astream` raising `RuntimeError` → emits `stream_start` → … → `error{reason:"internal"}` → `stream_end{source:"error", final_report:""}` in order |
| T9 | `tests/unit/test_research_router.py` | NEW | Generator with simulated timeout (monkeypatch `RESEARCH_TIMEOUT_S=1` + slow mock agent) → emits `error{reason:"timeout", recoverable:True}` → `stream_end{source:"error"}` |
| T10 | `tests/unit/test_research_router.py` | NEW | On success path, `stream_end.final_report_source == "stream"` and no `error` event emitted (contract guard) |
| T11 | `tests/unit/test_research_router.py` | AMEND | Existing fallback-draft test: assert `final_report_source == "file"` works; no `error` emitted |
| T12 | `tests/e2e/test_research_endpoint.py` | NEW | ASGI integration test with `RESEARCH_TIMEOUT_S=1` + slow mock agent → HTTP 200 SSE stream containing `stream_start → … → error{reason:"timeout"} → stream_end{source:"error"}` |
| T13 | `tests/e2e/test_research_endpoint.py` | AMEND | Existing event-sequence e2e test passes unchanged |
| T14 | `tests/unit/test_chunk_mapper.py` (27 existing tests) | REGRESSION | All pass unchanged — chunk mapper not touched |

### 8.2 Frontend tests (vitest)

| # | File | Kind | Test |
| :-: | :--- | :-: | :--- |
| T15 | `useResearchStream.test.ts` | NEW | Reducer: `error` event with `{reason: "timeout", recoverable: true, message}` → state has `errorReason === "timeout"`, `errorRecoverable === true`, `error === message`, `status === "error"` |
| T16 | `useResearchStream.test.ts` | NEW | Reducer: state-after-error + `stream_end{final_report_source: "error"}` → status stays `"error"`, `reportSource === "error"`, todos/files/subagents unchanged, no transition to `"done"` **(SPECIFICATION ANCHOR — see §8.4)** |
| T17 | `useResearchStream.test.ts` | NEW | Reducer: success-path `stream_end{final_report_source: "stream"}` → `status: "done"`, `report === data.final_report`, todos force-completed (regression) |
| T18 | `useResearchStream.test.ts` | NEW | Reducer: success-path `stream_end{final_report_source: "file"}` → `reportSource: "file"` (regression) |
| T19 | `next build` | IMPLICIT | TypeScript compile fails if anything references the removed `memory_updated` key |

### 8.3 Testing infrastructure

| Need | Approach |
| :--- | :--- |
| Mock agent raising on `astream` iteration | Reuse existing `tests/unit/test_research_router.py` pattern; add `failing_agent(exception_class)` factory fixture |
| Mock agent sleeping longer than timeout | New fixture `slow_agent(sleep_s)` using `asyncio.sleep` in an async generator |
| Short timeout override per test | `monkeypatch.setattr(settings, "RESEARCH_TIMEOUT_S", 1)` scoped per fixture |
| Collect events from generator | Helper `async def collect_events(generator) -> list[dict]` (likely already exists in existing router tests) |
| Frontend "state-after-error" helper | Small helper `stateAfterError()` feeding the reducer an `error` event and returning the state |

### 8.4 Test #16 is a specification anchor

Test #16 is the most important test in this plan. It codifies the design decision that `stream_end` is the terminal signal and `error` is the status-transition signal — a decision subtle enough that a future refactor could easily get it backward. Mark the test with a comment pointing to this spec so the intent travels with the code:

```typescript
// DESIGN: Per docs/superpowers/specs/2026-04-24-phase-0-stabilize-sse-contract-design.md §4.3,
// stream_end with final_report_source === "error" must NOT transition state to "done"
// because the preceding `error` event already set status:"error". Removing this branch
// breaks the contract guarantee in §4.4.
it("preserves error status on stream_end after error", () => {
  ...
});
```

### 8.5 Deliberate non-tests

| Skipped | Why |
| :--- | :--- |
| Test that `asyncio.timeout` itself works | Python stdlib — not our contract |
| Test mid-stream client disconnect | SSE/sse-starlette behavior; testing requires fragile async cancellation plumbing |
| Test `traceback.format_exc()` content | Python stdlib; visible via grep if broken |
| Test `ERROR_MESSAGES` string contents | Copy-paste from catalog; snapshot test adds noise without catching real bugs |
| Test invalid `reason` string at runtime | Covered by mypy + TypeScript strict |

### 8.6 Coverage goal

New code (router generator, events factory, settings field) ≥ 95% line coverage. Only acceptable uncovered line: the `except Exception` within the `aget_state` inner try/except (pre-existing logic, harmless to leave untested).

Total: ~19 new/amended tests, ~250 LOC of test code.

### 8.7 Manual smoke verification

Before merge, one developer runs locally:

1. Start backend + frontend: `cd apps/api && uvicorn app.main:app --reload --port 8000` / `cd apps/web && npm run dev`.
2. Submit a legitimate question → `status: "done"` with report rendered.
3. Temporarily set `RESEARCH_TIMEOUT_S=5` in `.env`, restart API, submit a complex question → timeout fires, UI shows "Research timed out." message, status stuck at `"error"`, UI is not stuck in `"streaming"`.
4. Disconnect network briefly mid-stream → frontend preserves last-known state, reconnect → re-submit works.
5. Confirm no `memory_updated` event appears in terminal logs.

Step 3 is the credibility check for the CHANGELOG "Fixed" bullet — CI cannot replace this 3-minute manual loop.

## 9. Rollout

### 9.1 PR mechanics

| Aspect | Value |
| :--- | :--- |
| Branch | `fix/phase-0-stabilize-sse-contract` |
| Commit strategy | Small reviewable commits on branch; squash-merge to `main` |
| PR title | `fix(api,web): stabilize SSE contract + timeout + remove memory_updated` |
| PR body | Summary + Test Plan + "Closes #2" footer |
| Milestone | Attached via issue #2 auto-close on merge |
| Hooks | Never skipped (`--no-verify` forbidden per CLAUDE.md) |

### 9.2 CI gates

1. `ruff check .` clean
2. `ruff format --check .` clean
3. `mypy app/` clean
4. `pytest` passes (full suite)
5. `npm run lint` clean
6. `npm run format:check` clean
7. `next build` succeeds
8. `npm test` passes (full vitest suite)

### 9.3 Reviewer checklist

```markdown
- [ ] Contract changes match design spec §4 exactly
- [ ] `grep -r memory_updated` returns 0 results across the repo
- [ ] `RESEARCH_TIMEOUT_S` validation bounds (10–3600) present
- [ ] Router generator has `try/except/finally` with `stream_end` in `finally`
- [ ] `error` factory takes only `reason`; message from catalog
- [ ] No `str(e)` sent to client — only logged
- [ ] Reducer `stream_end` has `if final_report_source === "error"` early return
- [ ] CHANGELOG.md populated with all six bullets from spec §7.1
- [ ] CONTRIBUTING.md has new Changelog section in right place
- [ ] `.env.example` has `RESEARCH_TIMEOUT_S=500` line
- [ ] Manual smoke (spec §8.7) performed; outcome posted as PR comment
- [ ] Existing 27 chunk_mapper tests pass unchanged
- [ ] Existing e2e event-sequence tests pass unchanged
```

## 10. Rollback

**One-command rollback** is a primary design constraint:

```bash
git revert <merge-commit-sha>
git push origin main
```

Restores:
- Original router generator (no timeout, error without stream_end).
- Original event factories (with `memory_updated`).
- Original `SSEEventMap` (with `memory_updated`).
- `CHANGELOG.md` absent (acceptable; Phase 1 recreates it).

**No migrations, no DB changes, no env-var renames** — revert has no side effects beyond restoring the prior SSE contract. In-flight requests during the revert window get whichever code their connection landed on; new connections get reverted behavior.

## 11. Risk register

| Risk | Likelihood | Blast radius | Mitigation |
| :--- | :-: | :-: | :--- |
| `deepagents 0.5.2` subtle behavior change | Low | High | Full test suite on PR branch; chunk_mapper's 27 tests as canary |
| `asyncio.timeout` × `agent.astream` interaction | Medium | High | Test T9 + manual smoke step 3 |
| 500 s too short for production edge cases | Low | Medium | Env var increase (`RESEARCH_TIMEOUT_S=1200`) — no code change |
| Reducer misses no-op error branch → UI flips to "done" | Medium | Low | Test T16 (specification anchor); reviewer checklist explicitly calls out |
| Exception details leak via `logger.error` to future log aggregator | Low | Low-Medium | No Phase 0 logging infra change; Phase 1 addresses properly |
| Client disconnects during finally emission | Low | None | sse-starlette handles cleanly; no mitigation needed |

## 12. Post-merge verification window

For 48 hours after merge (before Phase 1 tracing lands):

1. **Daily local smoke**: 2–3 research questions of varying length; all reach `"done"` with visible report.
2. **Weekly error-path smoke**: temporarily set `RESEARCH_TIMEOUT_S=15`; submit complex questions to force timeouts; confirm graceful UI.
3. **Log grep**: scan `uvicorn --reload` terminal output for unexpected exception patterns.

Once Phase 1 ships LangSmith tracing, these become automatic dashboard checks.

## 13. Open questions (none for Phase 0)

All design decisions were resolved during brainstorming. The four open questions parked in the milestones doc §9 belong to later phases:

- Phase 2b: `approval_required` timeout behavior.
- Phase 3b: Per-user MCP auth timing.
- Phase 4: Per-run sandbox call cap.
- Phase 5: Judge model choice.

These do not block Phase 0 implementation.

## 14. Related work

- **Issue**: [#2 Phase 0: Stabilize SSE contract, add timeout, bump deepagents to 0.5](https://github.com/minhtran3124/chat-agents/issues/2)
- **Milestone**: [#1 Deep Agents Harness Upgrade — Hybrid Path](https://github.com/minhtran3124/chat-agents/milestone/1)
- **Roadmap**: [`reseachers/deep-agents-harness-upgrade-roadmap.md`](../../../reseachers/deep-agents-harness-upgrade-roadmap.md) — hybrid-stance analysis
- **Milestones doc**: [`reseachers/deep-agents-harness-upgrade-milestones.md`](../../../reseachers/deep-agents-harness-upgrade-milestones.md) §5 Phase 0 — acceptance source
- **Vietnamese mirror**: [`reseachers/deep-agents-harness-upgrade-milestones.vi.md`](../../../reseachers/deep-agents-harness-upgrade-milestones.vi.md)

## 15. Next steps

1. Spec-document-reviewer pass on this file (automated validation).
2. User review of this file.
3. On approval: invoke `writing-plans` skill to produce `docs/superpowers/plans/2026-04-24-phase-0-implementation-plan.md`.
4. Plan drives implementation PR on branch `fix/phase-0-stabilize-sse-contract`.
