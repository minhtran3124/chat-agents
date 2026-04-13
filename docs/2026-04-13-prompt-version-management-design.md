# Design Spec — Prompt Version Management

**Status:** Draft
**Author:** Minh Tran
**Date:** 2026-04-13
**Related:** [`agent_factory.py`](../apps/api/app/services/agent_factory.py), [`research.py`](../apps/api/app/routers/research.py)

---

## 1. Goal

Replace the three hardcoded prompt constants in `agent_factory.py` with a
file-backed versioning system that supports:

1. **Per-request prompt override** — send `{"main": "v2"}` on a request to
   test a specific variant without changing anything server-side.
2. **Production defaults via `active.yaml`** — one file declares which version
   is the live default per prompt; changing it is a one-line git commit.
3. **Audit logging** — every stream logs which prompt versions actually ran,
   and the `stream_end` SSE event carries `versions_used` so the FE can
   display it.
4. **Hot-reload** — `registry.reload()` re-reads files from disk without
   restarting the server, useful during local iteration.

Git is the primary version store. All prompt files live in the repo.

---

## 2. Non-Goals

- UI for editing prompts (prompts are edited as files, committed to git)
- Database storage for prompts
- Automatic A/B traffic splitting (per-request override covers the testing use
  case without a traffic router)
- Semantic versioning / semver ranges (simple `v1`, `v2`, `v2-concise` names
  are sufficient)
- Prompt evaluation metrics (out of scope; this spec covers storage, loading,
  resolution, and logging only)

---

## 3. Folder Structure

```
prompts/                          ← new top-level directory in repo root
├── active.yaml                   ← production defaults
├── main/
│   ├── v1.md                     ← migrated from MAIN_PROMPT constant
│   └── v2.md                     ← new variant for testing
├── researcher/
│   ├── v1.md                     ← migrated from RESEARCHER_PROMPT constant
│   └── v2.md
└── critic/
    └── v1.md                     ← migrated from CRITIC_PROMPT constant
```

**File format:** plain `.md` — no frontmatter, no YAML. Git provides author,
date, and diff history. The filename stem is the version key.

**Version naming convention:** `v1`, `v2`, `v3` for sequential iterations;
`v2-concise`, `v2-citations-first` for named experiments. Any filename stem
is valid.

**`active.yaml` format:**

```yaml
main: v1
researcher: v1
critic: v1
```

One entry per known prompt name. Changing a value and committing is the
production rollback/promotion mechanism.

---

## 4. `PromptRegistry` Service

**File:** `apps/api/app/services/prompt_registry.py`

A module-level singleton. Loads all prompt files at import time; re-reads on
`reload()`.

### 4.1 Internal State

```python
_prompts: dict[str, dict[str, str]]
# {"main": {"v1": "<text>", "v2": "<text>"}, "researcher": {...}, ...}

_active: dict[str, str]
# {"main": "v1", "researcher": "v1", "critic": "v1"}
```

### 4.2 Public Interface

```python
class PromptRegistry:
    def get(self, name: str, version: str | None = None) -> str:
        """Return prompt text. Uses active version when version=None."""

    def resolve_versions(self, overrides: dict[str, str]) -> dict[str, str]:
        """Merge overrides with active defaults. Returns resolved {name: version}."""

    def list_versions(self, name: str) -> list[str]:
        """Return sorted list of available version keys for a prompt name."""

    def active_versions(self) -> dict[str, str]:
        """Return a copy of the active.yaml mapping."""

    def reload(self) -> None:
        """Re-read all files and active.yaml from disk."""

# Module-level singleton — import and use directly
registry = PromptRegistry(prompts_dir=Path(__file__).parents[3] / "prompts")
```

### 4.3 Error Contract

| Condition | Behaviour |
|---|---|
| Unknown prompt `name` | `KeyError`: "Unknown prompt 'X'. Available: main, researcher, critic" |
| Unknown `version` for a known name | `KeyError`: "Unknown version 'v9' for 'main'. Available: v1, v2" |
| `active.yaml` missing entry for a prompt | Warn and fall back to `v1` |
| `active.yaml` file missing entirely | `RuntimeError` at startup: "prompts/active.yaml not found" |
| `prompts/` directory missing | `RuntimeError` at startup with clear path |
| Empty `.md` file | `ValueError`: "Prompt file 'main/v2.md' is empty" |

### 4.4 Startup Wiring

`app/main.py` lifespan calls `registry.reload()` on startup to surface any
file errors before the first request arrives:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    registry.reload()          # fail fast if prompts/ is missing or malformed
    async with lifespan_stores():
        yield
```

---

## 5. Schema Change

**File:** `apps/api/app/schemas/research.py`

```python
class ResearchRequest(BaseModel):
    question: str
    thread_id: str | None = None
    prompt_versions: dict[str, str] | None = None
    # e.g. {"main": "v2", "researcher": "v2-concise"}
    # None or omitted → active.yaml defaults apply for all prompts
```

Unknown keys in `prompt_versions` are ignored (the registry raises on
resolution only for keys that match known prompt names).

---

## 6. `agent_factory` Change

**File:** `apps/api/app/services/agent_factory.py`

Remove module-level constants. `build_research_agent()` accepts resolved
prompt strings:

```python
def build_research_agent(
    main_prompt: str,
    researcher_prompt: str,
    critic_prompt: str,
) -> Any:
    ...
```

No registry dependency inside the factory — the factory remains a pure
constructor. Version resolution is the router's responsibility.

---

## 7. Router Change

**File:** `apps/api/app/routers/research.py`

Resolution, logging, and factory call happen before the generator is created:

```python
@router.post("")
async def research(payload: ResearchRequest) -> EventSourceResponse:
    overrides = payload.prompt_versions or {}
    versions_used = registry.resolve_versions(overrides)
    logger.info("[RESEARCH] prompt_versions=%s", versions_used)

    agent = build_research_agent(
        main_prompt=registry.get("main", version=versions_used["main"]),
        researcher_prompt=registry.get("researcher", version=versions_used["researcher"]),
        critic_prompt=registry.get("critic", version=versions_used["critic"]),
    )
    ...
```

`versions_used` is also passed into the `stream_end` SSE event alongside
`usage`, so the frontend can display which versions produced the report.

---

## 8. SSE Event Change

**File:** `apps/api/app/streaming/events.py`

`stream_end` gains a `versions_used` field:

```python
def stream_end(
    final_report: str,
    usage: dict[str, Any],
    versions_used: dict[str, str],
) -> dict:
    return _sse("stream_end", {
        "final_report": final_report,
        "usage": usage,
        "versions_used": versions_used,
    })
```

Frontend `types.ts` adds `versions_used` to the `stream_end` SSE type so it
can be displayed in the dashboard.

---

## 9. Migration Steps

1. Create `prompts/` directory with `active.yaml` and three subdirectories.
2. Copy the text of each constant from `agent_factory.py` into its `v1.md`
   file verbatim.
3. Implement `PromptRegistry` and add `registry.reload()` to lifespan.
4. Update `ResearchRequest` schema.
5. Update `build_research_agent()` signature.
6. Update router to resolve + log versions.
7. Update `stream_end` event and `types.ts`.
8. Delete the three module-level constants from `agent_factory.py`.
9. Update `agent_factory` unit tests to pass prompt strings directly.

---

## 10. Testing

- **Unit tests for `PromptRegistry`:** happy path, unknown name, unknown
  version, missing `active.yaml` entry, missing `active.yaml` file, empty
  `.md` file, reload after file change.
- **Unit tests for `resolve_versions` merge logic:** partial override (e.g.
  only `{"main": "v2"}` provided) must leave non-overridden prompts
  (`researcher`, `critic`) at their active defaults — this is the core
  correctness invariant of the override feature.
- **Unit tests for router:** verify `versions_used` is logged and included in
  `stream_end`; verify per-request override takes precedence over active
  default.
- **Manual A/B test workflow:**
  1. Create `prompts/main/v2.md` with revised prompt.
  2. Send a request with `{"prompt_versions": {"main": "v2"}}`.
  3. Compare report quality against a request without override (which runs v1).
  4. If v2 is better: update `active.yaml` → `main: v2`, commit, done.
  5. If not: delete v2.md or leave it; active.yaml unchanged.
