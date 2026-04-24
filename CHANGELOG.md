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
