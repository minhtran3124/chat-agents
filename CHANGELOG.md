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
- Per-agent token breakdown tracking: `ChunkMapper` now tracks cumulative tokens
  per agent role (main, researcher, critic) and respects OpenAI/Anthropic cache
  discount (50% of cached input tokens).
- `token_breakdown` SSE event emitted at stream completion with per-role token
  counts, enabling data-driven architecture exploration.
- `TokenBreakdownPanel` React component displaying token cost breakdown in the
  research dashboard sidebar with stacked progress bars and percentage labels.

### Changed
- `error` SSE event now carries sanitized per-reason messages from a static
  catalog; raw exception strings are logged server-side only. `recoverable`
  flag derives from `reason` (`"timeout" → true`, `"internal" → false`).
- `/research` now emits `stream_end` unconditionally via a `finally` block —
  a failed run no longer leaves the frontend reducer stuck in `"streaming"`.
- Relaxed component library policy: `shadcn/ui`, Radix, Headless UI, etc. are
  now allowed for complex interactive patterns (modals, dropdowns, tables).
  See `guidelines.md` → *Styling & Components* for adoption criteria.
- `MAX_TOKENS_PER_RUN` documented recommendation updated to 500k (from 200k
  default) to enable complete Deep Agents multi-topic research cycles.
- OpenAI default model updated from `gpt-4.1-mini` to `gpt-5.5`.

### Removed
- Orphan `memory_updated` SSE event — factory function, `SSEEventMap` entry,
  and type unused across both api and web. Future semantic-memory features
  will introduce a mem0-native `memory_operation` event (see
  `reseachers/deep-agents-harness-upgrade-milestones.md` §10 parking lot).
- `VFS_OFFLOAD_THRESHOLD_TOKENS` setting (dead code) — Tavily returns small
  snippets (~5k tokens), not full HTML, so VFS offload threshold never triggered.
  Correct approach: let agent request full content via tool when needed.
- `researcher/v3.md` prompt (documented non-existent behavior) — reverted to v2
  when VFS offload attempt was abandoned.

### Fixed
- Missing `stream_end` on mid-stream exceptions (`stream_end` is now
  guaranteed on every terminal path).
- Unbounded `/research` runtime — long hangs now fail fast at the timeout.
- Search cap implementation now uses `InjectedState` pattern for reliable
  per-agent search quota enforcement (4 searches per agent) across thread
  boundaries and checkpoint lifecycle.
