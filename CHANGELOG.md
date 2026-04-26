# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project uses an `[Unreleased]` section at the top where entries
accrue between releases. Each PR that changes user-visible behavior
updates this file; entries graduate to a dated version header when a
release is cut.

## [Unreleased]

### Changed
- Research dashboard main content layout: workflow tree and final response now
  display in a 2-column view (side-by-side) instead of stacked vertically,
  enabling users to correlate agent decisions with final output simultaneously.

## [0.2.0] - 2026-04-26

### Added
- Per-agent token breakdown tracking: `ChunkMapper` now tracks cumulative tokens
  per agent role (main, researcher, critic) and respects OpenAI/Anthropic cache
  discount (50% of cached input tokens).
- `token_breakdown` SSE event emitted at stream completion with per-role token
  counts, enabling data-driven architecture exploration.
- `TokenBreakdownPanel` React component displaying token cost breakdown in the
  research dashboard sidebar with stacked progress bars and percentage labels.

### Changed
- Relaxed component library policy: `shadcn/ui`, Radix, Headless UI, etc. are
  now allowed for complex interactive patterns (modals, dropdowns, tables).
  See `guidelines.md` → *Styling & Components* for adoption criteria.
- `MAX_TOKENS_PER_RUN` documented recommendation updated to 500k (from 200k
  default) to enable complete Deep Agents multi-topic research cycles.
- OpenAI default model updated from `gpt-4.1-mini` to `gpt-5.5`.

### Removed
- `VFS_OFFLOAD_THRESHOLD_TOKENS` setting (dead code) — Tavily returns small
  snippets (~5k tokens), not full HTML, so VFS offload threshold never triggered.
  Correct approach: let agent request full content via tool when needed.
- `researcher/v3.md` prompt (documented non-existent behavior) — reverted to v2
  when VFS offload attempt was abandoned.

### Fixed
- Search cap implementation now uses `InjectedState` pattern for reliable
  per-agent search quota enforcement (4 searches per agent) across thread
  boundaries and checkpoint lifecycle.

## [0.1.0] - 2026-04-24

### Added
- `RESEARCH_TIMEOUT_S` setting (default 500s, bounded 10–3600) enforced around
  agent streaming via `asyncio.timeout`. Long-running queries now fail fast.
- `MAX_TOKENS_PER_RUN` setting with token budget guard that aborts runs
  exceeding the limit and emits `budget_exceeded` event before `stream_end`.
- `budget_exceeded` SSE event carrying token usage, limit, and recovery message.
- `reason` field on the `error` SSE event with values `"timeout" | "internal" | "rate_limited"`.
- `"error"` variant on `stream_end.final_report_source` to distinguish terminal failures.
- `token_count` extraction helper respecting OpenAI/Anthropic cache discount
  (cached input billed at 50% rate).
- This `CHANGELOG.md` file and its convention (documented in `CONTRIBUTING.md`).
- Structured logging via `structlog`: request context middleware binds `request_id`,
  endpoint logs carry `prompt_versions` and execution metrics.
- `RequestContextMiddleware` for automatic `request_id` binding across request scope.
- `ErrorView` React component with budget exceeded (warn) and error (danger) variants.
- Reflection timeline in research dashboard: `think_tool` calls render as timestamped
  reflections grouped by agent role.
- `think_tool` for reflective research loops: agents can pause and reason before
  continuing (surfaces as `reflection_logged` SSE events).

### Changed
- `error` SSE event now carries sanitized per-reason messages from a static
  catalog; raw exception strings are logged server-side only. `recoverable`
  flag derives from `reason` (`"timeout" → true`, `"internal" → false`,
  `"rate_limited" → true`).
- `/research` now emits `stream_end` unconditionally via a `finally` block —
  a failed run no longer leaves the frontend reducer stuck in `"streaming"`.
- Research dashboard redesigned as "Research Journal" with pinned question card,
  sidebar panels (todos, subagents, reflections, files), and main content area.
- UI theme refreshed with teal accent, neutral grays, and Tailwind semantics.

### Removed
- Orphan `memory_updated` SSE event — factory function, `SSEEventMap` entry,
  and type unused across both api and web. Future semantic-memory features
  will introduce a mem0-native `memory_operation` event (see
  `reseachers/deep-agents-harness-upgrade-milestones.md` §10 parking lot).

### Fixed
- Missing `stream_end` on mid-stream exceptions (`stream_end` is now
  guaranteed on every terminal path).
- Unbounded `/research` runtime — long hangs now fail fast at the timeout.
- Subagent detection now stable via `tool_call_id` matching (replaces fragile
  role inference based on task name presence).
- SSE CRLF parsing (sse-starlette default) now handled correctly on frontend.
- Unwrapped LangGraph `Overwrite` channel annotations on `messages` field.

## [0.0.1] - 2026-04-13

### Added
- **Backend (FastAPI + LangGraph Deep Agents)**:
  - Provider-agnostic LLM factory (Anthropic, OpenAI, Google) with model
    resolution and environment export for 3rd-party libraries.
  - Tavily search tool wrapped as LangChain tool with configurable results.
  - SQLite checkpointer with in-memory cross-session store.
  - Research agent factory: orchestrates main agent + researcher + critic subagents.
  - 10 SSE event types: `stream_start`, `todo_updated`, `file_saved`, `subagent_started`,
    `subagent_completed`, `compression_triggered`, `text_delta`, `reflection_logged`,
    `stream_end`, `error`.
  - Stateful chunk mapper: transforms LangGraph stream output
    (`messages`, `updates`, `values` modes) into typed SSE events.
  - Research SSE endpoint with synthetic compression fallback (30k token threshold).
  - Ruff + mypy + pytest configuration with type checking and test markers.

- **Frontend (Next.js 14 + React 18)**:
  - SSE parser for handling text/event-stream CRLF/LF framing.
  - `useResearchStream` hook: fetch + SSE parsing → component state.
  - Research dashboard with todo list, file tracker, and subagent panel.
  - Markdown report view with GitHub-flavored markdown (remark-gfm) + prose styling.
  - TypeScript strict mode with SSEEventMap discriminated union for events.
  - Tailwind CSS 3.4 + prettier formatting with class sorting.
  - Server component default pattern (Next.js App Router).

- **Project Infrastructure**:
  - Monorepo layout: `apps/api/` (FastAPI) and `apps/web/` (Next.js) with
    independent package managers (pip + npm, no workspace).
  - CONTRIBUTING.md: commit conventions, tool commands, test markers.
  - CLAUDE.md: Claude Code rules, project conventions, MCP tools guidance.
  - ARCHITECTURE.md: component responsibilities, request flow, key patterns.
  - Prompt versioning system: file-backed `prompts/` with `active.yaml` + per-request overrides.
  - EditorConfig for cross-editor baseline.

### Changed
- (none in initial release)

### Removed
- (none in initial release)

### Fixed
- setuptools package discovery and entry points for egg-info generation.
- Ruff/mypy lint issues across tests and services.
- Streaming robustness in chunk mapper: handle missing/nil fields gracefully.
- CRLF frame parsing in SSE client.
