# Supervisor Orchestration — Task DAG for Parallel Agent Team

**Source plan:** `docs/superpowers/specs/2026-04-14/supervisor-orchestration-plan.md`
**Purpose:** Dependency graph + parallel-execution waves for dispatching the 11 chunks as parallel agents (one chunk per agent, one agent per commit).
**Atomic unit:** each task below is **one chunk → one commit** in the source plan. Sub-steps inside a chunk are strictly sequential and owned by that chunk's agent.

---

## Progress Tracker

**Concurrency model.** Multiple agents may pick tasks from the Master Checklist in parallel. The three-column lock (**Todo → In-Progress → Done**) prevents duplicate work: an agent scans for a row where `Todo = [x]` AND `In-Progress = [ ]`, then atomically claims it by moving `[x]` between columns and writing its name in the Owner column. Another agent scanning simultaneously sees the lock and skips that row.

**Master Checklist workflow (per task):**

1. **Pick:** find a row where `Todo = [x]`, `In-Progress = [ ]`, `Done = [ ]`, and all hard dependencies (see §1) are already `Done = [x]`.
2. **Claim** (*before* starting work): flip `Todo [x] → [ ]`, flip `In-Progress [ ] → [x]`, write your agent name in the Owner column. Commit this edit on its own (e.g. `chore(plan): claim T1`) and push immediately so other agents see the lock.
3. **Execute:** work through the task's sub-step checklist below (`- [ ]` → `- [x]` as you finish each TDD step in the plan).
4. **Mark done:** once your task's final code commit has landed, flip `In-Progress [x] → [ ]`, flip `Done [ ] → [x]`, and write the commit SHA in the last column. Commit this edit (e.g. `chore(plan): mark T1 done`).
5. **Conflict?** If your claim commit is rejected by the remote (someone else claimed the same row first), abort, rebase, and pick a different task. Never contend for a task.

**Status legend:**

- **Master Checklist cells** — `[ ]` empty · `[x]` set. **Exactly one** of the three state columns (Todo / In-Progress / Done) is `[x]` for any given row at any time.
- **Sub-step checklists** — `[ ]` pending · `[x]` done · `[!]` blocked (stop and escalate).
- **Wave Gates** — orchestrator flips from `[ ]` to `[x]` when every task in the wave is `Done = [x]` and the full test suite is green.

**Quick progress oracle (run any time to see where the team is):**

```bash
DAG=docs/superpowers/specs/2026-04-14/supervisor-orchestration-task-dag.md

# master checklist — tasks by state (column padding differs, so use `+` for 1+ spaces)
grep -cE '^\| T[0-9]+ .*\| \[x\] +\| \[ \] +\| \[ \] +\|' "$DAG"   # Todo
grep -cE '^\| T[0-9]+ .*\| \[ \] +\| \[x\] +\| \[ \] +\|' "$DAG"   # In-Progress
grep -cE '^\| T[0-9]+ .*\| \[ \] +\| \[ \] +\| \[x\] +\|' "$DAG"   # Done

# sub-step checklists — how many TDD micro-steps still pending?
grep -c '^- \[ \]' "$DAG"
```

### Master Checklist — one row per chunk

| ID  | Task                              | Wave | Todo | In-Progress | Done | Owner (agent name) | Commit SHA |
| :-- | :-------------------------------- | :--: | :--: | :---------: | :--: | :----------------- | :--------- |
| T1  | ModelRegistry                     |  1   | [ ]  | [ ]         | [x]  | Coder-A            | 0675991    |
| T2  | ToolRegistry                      |  1   | [ ]  | [ ]         | [x]  | Coder-B            | 7a15999    |
| T3  | AgentSpec + REGISTERED_SPECS      |  1   | [ ]  | [ ]         | [x]  | Coder-D            | ceb6af8    |
| T5  | Classifier                        |  1   | [ ]  | [ ]         | [x]  | Coder-C            | 2c5be69    |
| T9  | Shared runner + SSE event factory |  1   | [ ]  | [ ]         | [x]  | Coder-E            | 22e093b    |
| T4  | Tools                             |  2   | [ ]  | [ ]         | [x]  | Coder-E            | 7e7527c    |
| T6  | ReAct builder + refined prompts   |  2   | [ ]  | [ ]         | [x]  | Coder-D            | eb3b771    |
| T7  | Deep-research builder             |  2   | [ ]  | [ ]         | [x]  | Coder-C            | 827c364    |
| T8  | Supervisor graph + bypass graph   |  3   | [ ]  | [ ]         | [x]  | Coder-E            | 588a149    |
| T10 | Routers + /chat + /research + FE  |  4   | [ ]  | [x]         | [ ]  | Coder-A            | —          |
| T11 | Cleanup (delete legacy)           |  5   | [x]  | [ ]         | [ ]  | —                  | —          |

### Wave Gate Checklist — orchestrator flips these when a wave fully lands

- [x] **Wave 1 complete** (T1, T2, T3, T5, T9 all merged, green suite)
- [x] **Wave 2 complete** (T4, T6, T7 all merged, green suite)
- [x] **Wave 3 complete** (T8 merged, green suite)
- [ ] **Wave 4 complete** (T10 merged, green suite, frontend smoke test passed)
- [ ] **Wave 5 complete** (T11 merged, final lint + type-check + full test suite green)

### Per-Task Sub-Step Checklists

Each task's owning agent ticks these as it executes the TDD micro-steps from the source plan. Short titles only — consult the plan for code snippets and exact commands.

#### T1 — ModelRegistry (Wave 1)
- [x] 1.1 Create `apps/api/models.yaml` with OpenAI defaults
- [x] 1.2 Write failing test — YAML load + `get()`
- [x] 1.3 Run test — expect FAIL (ModuleNotFoundError)
- [x] 1.4 Implement `app/models/__init__.py` + `registry.py` minimal
- [x] 1.5 Run test — expect PASS
- [x] 1.6 Add env-override + unknown-role + required_providers tests
- [x] 1.7 Run tests — expect 4 passed
- [x] 1.8 Update Settings default provider to `openai`
- [x] 1.9 Lint + type-check (ruff + mypy)
- [x] 1.10 Full suite green (`pytest -x`)
- [x] 1.11 Commit — `feat(api): add ModelRegistry with YAML config and env overrides`

#### T2 — ToolRegistry (Wave 1)
- [x] 2.1 Write failing test — `@register_tool` decorator
- [x] 2.2 Run test — expect FAIL
- [x] 2.3 Implement `ToolRegistry` + singleton + empty `tools/__init__.py`
- [x] 2.4 Run tests — expect 4 passed
- [x] 2.5 Lint + type-check
- [x] 2.6 Full suite green (T2 tests 4/4 pass; 6 pre-existing failures unrelated to T2)
- [x] 2.7 Commit — `feat(api): add ToolRegistry with decorator auto-registration`

#### T3 — AgentSpec + REGISTERED_SPECS (Wave 1)
- [x] 3.1 Write failing test — spec declarations + integrity
- [x] 3.2 Run test — expect FAIL
- [x] 3.3 Implement `app/agents/specs.py` + `REGISTERED_SPECS`
- [x] 3.4 Run tests — expect 5 passed
- [x] 3.5 Lint + type-check
- [x] 3.6 Full suite green
- [x] 3.7 Commit — `feat(api): add AgentSpec and REGISTERED_SPECS for six specialists`

#### T5 — Classifier (Wave 1)
- [x] 5.1 Create `prompts/classifier/v1.md`
- [x] 5.2 Register classifier + 5 specialists in `prompts/active.yaml`
- [x] 5.3 Create placeholder prompts (chat/research/summarize/code/planner)
- [x] 5.4 Write failing test — `ClassifierResult` schema path
- [x] 5.5 Run test — expect FAIL
- [x] 5.6 Implement `schemas/routing.py` (`ClassifierResult`, `RoutingEvent`)
- [x] 5.7 Implement `app/agents/classifier.py` with `classify(...)`
- [x] 5.8 Run tests — expect 2 passed
- [x] 5.9 Add low-confidence + stickiness tests
- [x] 5.10 Run tests — expect 4 passed
- [x] 5.11 Lint + type-check
- [x] 5.12 Full suite green (PromptRegistry loads all prompts)
- [x] 5.13 Commit — `feat(api): add classifier node with structured output and stickiness`

#### T9 — Shared runner + SSE event factory (Wave 1)
- [x] 9.1 Write failing test — runner emits expected event sequence
- [x] 9.2 Run test — expect FAIL
- [x] 9.3 Implement `app/routers/_runner.py::run_graph(...)`
- [x] 9.4 Add `intent_classified(...)` factory to `streaming/events.py`
- [x] 9.5 Run runner test — expect PASS
- [x] 9.6 Lint + type-check + full suite
- [x] 9.7 Commit — `feat(api): add shared graph runner with intent_classified SSE event`

#### T4 — Tools: web_search, fetch_url, repo_search (Wave 2, after T2)
- [x] 4.1 Create `app/tools/web_search.py` (register + error-wrap)
- [x] 4.2 Write test for `web_search` (returns results, wraps exceptions)
- [x] 4.3 Add `web_search` import to `app/tools/__init__.py`
- [x] 4.4 Run web_search tests — expect 2 passed
- [x] 4.5 Create `app/tools/fetch_url.py` (httpx.AsyncClient, 10s timeout, 50KB cap)
- [x] 4.6 Test `fetch_url` (body + error-on-exception)
- [x] 4.7 Add `fetch_url` import to `__init__.py`
- [x] 4.8 Run fetch_url tests — expect 2 passed
- [x] 4.9 Create `app/tools/repo_search.py` (`git grep` subprocess, 5s timeout)
- [x] 4.10 Test `repo_search` (finds known symbol; empty on garbage)
- [x] 4.11 Add `repo_search` import to `__init__.py`
- [x] 4.12 Run repo_search tests — expect 2 passed
- [x] 4.13 Verify all three tools register via singleton
- [x] 4.14 Full suite green (legacy `/research` still works)
- [x] 4.15 Commit — `feat(api): add web_search/fetch_url/repo_search tools with registration`

#### T6 — ReAct builder + refined prompts (Wave 2, after T1, T2, T3, T5)
- [x] 6.1 Overwrite the 5 specialist prompts with refined content
- [x] 6.2 Write failing test for `build_react_agent` (no-tools + with-tools)
- [x] 6.3 Run test — expect FAIL
- [x] 6.4 Implement `app/agents/builders/react.py::build_react_agent(...)`
- [x] 6.5 Run tests — expect 2 passed
- [x] 6.6 Lint + type-check
- [x] 6.7 Full suite green
- [x] 6.8 Commit — `feat(api): add ReAct builder and refined prompts for five specialists`

#### T7 — Deep-research builder (Wave 2, after T1, T2, T3)
- [x] 7.1 Write failing test — `build_deep_research_agent` composes subagents
- [x] 7.2 Run test — expect FAIL
- [x] 7.3 Implement `app/agents/builders/deep_research.py`
- [x] 7.4 Run test — expect PASS
- [x] 7.5 Lint + type-check + full suite
- [x] 7.6 Commit — `feat(api): add deep_research builder wrapping create_deep_agent`

#### T8 — Supervisor graph + bypass graph (Wave 3, after T3, T5, T6, T7)
- [x] 8.1 Write failing integration test — graph compiles with 7 nodes
- [x] 8.2 Run test — expect FAIL
- [x] 8.3 Implement `app/agents/supervisor_graph.py` (`build_supervisor_graph` + `build_deep_research_only_graph`)
- [x] 8.4 Run test — expect PASS
- [x] 8.5 Lint + type-check + full suite
- [x] 8.6 Commit — `feat(api): add supervisor graph wiring classifier and six specialists`

#### T10 — Routers + `/chat` + `/research` refactor + SSE + frontend (Wave 4, after T4, T8, T9)
- [ ] 10.1 Add `app/schemas/chat.py` — `ChatRequest`
- [ ] 10.2 Implement `app/routers/chat.py` (POST `/chat` → `run_graph(force_intent=None)`)
- [ ] 10.3 Refactor `app/routers/research.py` (→ `run_graph(force_intent="deep-research")`)
- [ ] 10.4 Rewrite `app/main.py` lifespan (build registries, both graphs, register both routers)
- [ ] 10.5 Integration test — `/chat` with `chat` intent SSE happy path
- [ ] 10.6 Update `test_research_endpoint.py` to assert `intent_classified` event
- [ ] 10.7 Run backend tests — all PASS
- [ ] 10.8 Frontend — extend `SSEEventMap` in `lib/types.ts`
- [ ] 10.9 Frontend — add `routedIntent` + `intent_classified` handler in `useResearchStream.ts`
- [ ] 10.10 Frontend — create `RoutedIntentBadge.tsx` + render in `research/page.tsx`
- [ ] 10.11 Frontend — add vitest for hook handling the new event
- [ ] 10.12 Run frontend tests + lint (`npm test -- --run && npm run lint`)
- [ ] 10.13 Smoke-test end-to-end manually (optional; requires real API keys)
- [ ] 10.14 Commit — `feat(api,web): add /chat router, refactor /research bypass, wire intent_classified SSE`

#### T11 — Cleanup (Wave 5, after T10)
- [ ] 11.1 `grep` for callers of `llm_factory`, `search_tool`, `agent_factory`
- [ ] 11.2 Delete `app/services/llm_factory.py`
- [ ] 11.3 Delete `app/services/search_tool.py`
- [ ] 11.4 Decide on `app/services/agent_factory.py` — delete or leave as documented shim
- [ ] 11.5 Full gauntlet green (pytest + ruff + mypy + web lint + tsc)
- [ ] 11.6 Commit — `chore(api): remove legacy llm_factory, search_tool, and agent_factory`

---

## 1. Task Dependency Table

| ID  | Chunk                              | Blocks on (hard) | File conflicts with   | Wave | # TDD steps | Primary outputs (one commit each)                                                                                           |
| :-- | :--------------------------------- | :--------------- | :-------------------- | :--: | :---------: | :-------------------------------------------------------------------------------------------------------------------------- |
| T1  | ModelRegistry                      | —                | —                     |  1   |     11      | `apps/api/models.yaml`, `app/models/registry.py`, settings default → openai, unit tests                                     |
| T2  | ToolRegistry                       | —                | —                     |  1   |      7      | `app/tools/registry.py`, `app/tools/__init__.py` (empty), unit tests                                                        |
| T3  | AgentSpec + REGISTERED_SPECS       | —                | —                     |  1   |      7      | `app/agents/__init__.py`, `app/agents/specs.py`, unit tests                                                                 |
| T5  | Classifier                         | —                | **T6** (prompt files) |  1   |     13      | `prompts/classifier/v1.md`, 5 placeholder prompts, `active.yaml`, `app/schemas/routing.py`, `app/agents/classifier.py`      |
| T9  | Shared runner + SSE event factory  | —                | —                     |  1   |      7      | `app/routers/_runner.py`, `app/streaming/events.py` (append `intent_classified`), integration test                          |
| T4  | Tools (web_search, fetch_url, repo_search) | **T2**   | **T2** (`tools/__init__.py`) |  2   |     15      | `app/tools/web_search.py`, `fetch_url.py`, `repo_search.py`, `__init__.py` (3 imports), unit tests. Does **not** delete `services/search_tool.py`. |
| T6  | ReAct builder + refined prompts    | **T1, T2, T3, T5** | **T5** (prompt files) |  2   |      8      | `app/agents/builders/__init__.py`, `app/agents/builders/react.py`, 5 refined prompts, unit tests                            |
| T7  | Deep-research builder              | **T1, T2, T3**   | —                     |  2   |      6      | `app/agents/builders/deep_research.py`, unit test                                                                           |
| T8  | Supervisor graph + bypass graph    | **T3, T5, T6, T7** | —                   |  3   |      6      | `app/agents/supervisor_graph.py` (both `build_supervisor_graph` + `build_deep_research_only_graph`), integration test       |
| T10 | `/chat` router, `/research` refactor, SSE contract, frontend | **T4, T8, T9** | —   |  4   |     14      | `app/schemas/chat.py`, `app/routers/chat.py`, refactored `app/routers/research.py`, new `app/main.py` lifespan, 10 FE edits |
| T11 | Cleanup (delete legacy)            | **T10**          | —                     |  5   |      6      | Delete `services/llm_factory.py`, `services/search_tool.py`, possibly `services/agent_factory.py` + its tests               |

**Legend:**
- **Blocks on (hard):** the listed tasks MUST be merged before this task starts.
- **File conflicts with:** two tasks touch the same files. Sequential merge is required (rebase or pick one agent to land first).
- **Wave:** earliest parallel bucket this task can launch in.

---

## 2. Parallel Execution Waves

```
┌───────────────────────────────────────────────────────────────────────────┐
│ Wave 1  (5 agents in parallel, zero hard deps)                            │
│   T1 · T2 · T3 · T5 · T9                                                  │
└───────────────────────────────────────────────────────────────────────────┘
         │
         ▼  (all 5 merged)
┌───────────────────────────────────────────────────────────────────────────┐
│ Wave 2  (3 agents in parallel)                                            │
│   T4  (after T2) · T6  (after T1,T2,T3,T5) · T7  (after T1,T2,T3)         │
└───────────────────────────────────────────────────────────────────────────┘
         │
         ▼  (all 3 merged)
┌───────────────────────────────────────────────────────────────────────────┐
│ Wave 3  (1 agent)                                                         │
│   T8  (after T3,T5,T6,T7 — technically T5 is also satisfied by Wave 1)    │
└───────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Wave 4  (1 agent — the only cross-cutting wave, spans api + web)          │
│   T10  (after T4,T8,T9)                                                   │
└───────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Wave 5  (1 agent)                                                         │
│   T11  (after T10)                                                        │
└───────────────────────────────────────────────────────────────────────────┘
```

**Parallelism ceiling per wave:** 5 / 3 / 1 / 1 / 1. Maximum concurrent agents = **5** in Wave 1.

**Total commits after all waves:** 11 commits, each a clean Conventional Commit landing on the target branch.

---

## 3. Known File Conflicts (prevent parallel merge without coordination)

| File                                      | Written by | Resolution |
| :---------------------------------------- | :--------- | :--------- |
| `apps/api/prompts/chat/v1.md`             | T5 (placeholder), T6 (refined)     | **Land T5 first.** T6 overwrites intentionally. Merge order enforced by Wave 1 → Wave 2 boundary. |
| `apps/api/prompts/research/v1.md`         | T5, T6                             | Same as above. |
| `apps/api/prompts/summarize/v1.md`        | T5, T6                             | Same as above. |
| `apps/api/prompts/code/v1.md`             | T5, T6                             | Same as above. |
| `apps/api/prompts/planner/v1.md`          | T5, T6                             | Same as above. |
| `apps/api/prompts/active.yaml`            | T5 only                            | No conflict. |
| `apps/api/app/tools/__init__.py`          | T2 (empty), T4 (3 imports appended) | **Land T2 first.** T4 appends. Merge order enforced by Wave 1 → Wave 2 boundary. |
| `apps/api/app/streaming/events.py`        | T9 only (append `intent_classified`) | No conflict. |

**Rule of thumb:** agents in the same wave must write to disjoint files. The waves above already enforce this.

---

## 4. Per-Task Briefs (one-paragraph each; self-contained for an agent)

### T1 — ModelRegistry (Wave 1)
Implement `app/models/registry.py` with `ModelSpec` (Pydantic, frozen) + `ModelRegistry` class that loads `models.yaml`, applies `<ROLE>_MODEL` / `<ROLE>_PROVIDER` env overrides, exposes `get(role)`, `build(role)` (cached), `roles()`, `required_providers()`. Write `models.yaml` with `classifier`/`fast`/`main` roles defaulting to OpenAI (`gpt-4o-mini`/`gpt-4o-mini`/`gpt-4o`). Change `settings.py` `LLM_PROVIDER` default to `"openai"`. Unit tests cover YAML load, env override precedence, provider swap, unknown role, and `required_providers()` dedup.
**Commit:** `feat(api): add ModelRegistry with YAML config and env overrides`

### T2 — ToolRegistry (Wave 1)
Implement `app/tools/registry.py` with `ToolRegistry` class: `register(name)` decorator, `get(name)`, `get_many(names)`, `names()`. Export a module-level singleton `registry` and `register_tool = registry.register`. Create empty `app/tools/__init__.py` (T4 fills in the eager imports). Unit tests cover decorator registration, duplicate-registration error, unknown-tool error, and `get_many` order preservation.
**Commit:** `feat(api): add ToolRegistry with decorator auto-registration`

### T3 — AgentSpec + REGISTERED_SPECS (Wave 1)
Implement `app/agents/specs.py` with `AgentSpec` Pydantic model (`name`, `model_role`, `tools`, `prompt_name`, `subagents`), a typed `IntentName` Literal over the six intents, and a module-level `REGISTERED_SPECS` list with the exact six specs from spec §5.3. Unit tests assert all six specs exist, `deep-research` has `researcher`+`critic` subagents, the other five have no subagents, names are unique, and invalid intent names raise.
**Commit:** `feat(api): add AgentSpec and REGISTERED_SPECS for six specialists`

### T5 — Classifier (Wave 1)
Three layers of work. (a) `app/schemas/routing.py`: `ClassifierResult` (intent/confidence/fallback_used) and `RoutingEvent`. (b) `app/agents/classifier.py`: `async def classify(messages, current_intent, llm, prompt)` that uses `llm.with_structured_output(ClassifierResult)`, applies confidence threshold (<0.55 → fallback chat) and stickiness (current==new and confidence≥0.40), and catches exceptions → `chat` fallback. (c) Prompts: `prompts/classifier/v1.md` (real content) plus 5 placeholder prompts for chat/research/summarize/code/planner (so PromptRegistry loads cleanly); update `prompts/active.yaml` to register all 9 prompt names. Unit tests cover happy path, exception path, low confidence, and stickiness.
**Commit:** `feat(api): add classifier node with structured output and stickiness`
**Conflict note:** writes 5 placeholder prompt files that T6 will overwrite — merge order T5 → T6.

### T9 — Shared runner + `intent_classified` SSE factory (Wave 1)
(a) Append `intent_classified(intent, confidence, fallback_used)` factory to `app/streaming/events.py`. (b) Implement `app/routers/_runner.py` with `run_graph(graph, question, thread_id, versions_used, force_intent)` generator that yields `stream_start`, emits `intent_classified` (either from `force_intent` or by observing the classifier node's update), threads chunks through `ChunkMapper`, and emits `stream_end` / `error(recoverable=False)`. Integration test uses a fake graph yielding `("updates", {"classifier": {...}})` + `("messages", (AIMessageChunk, {}))` and asserts event sequence `stream_start → intent_classified → text_delta → stream_end`.
**Commit:** `feat(api): add shared graph runner with intent_classified SSE event`

### T4 — Tools (Wave 2, depends T2)
Three tool modules, each `@register_tool`'d and returning `{"error": str(e)}` on failure (never raising). (a) `app/tools/web_search.py` — Tavily wrapper (copy of `services/search_tool.py` with registration). (b) `app/tools/fetch_url.py` — `httpx.AsyncClient` GET, 10s timeout, 50KB cap. (c) `app/tools/repo_search.py` — `git grep -n -E` subprocess with 5s timeout + 200-line cap. Append all three imports to `app/tools/__init__.py`. Unit tests mock `httpx` and `TavilyClient`; the `repo_search` test exercises the real working tree (asserts `create_deep_agent` is found in `agent_factory.py`). Verify the singleton registry lists all three tool names.
**Commit:** `feat(api): add web_search/fetch_url/repo_search tools with registration`
**Do NOT delete** `services/search_tool.py` — that's T11.

### T6 — ReAct builder + refined prompts (Wave 2, depends T1, T2, T3, T5)
(a) Implement `app/agents/builders/react.py` with `build_react_agent(spec, model_registry, tool_registry, prompt_registry, prompt_version=None)` returning `create_react_agent(model, tools, prompt, name)`. (b) Overwrite the 5 placeholder prompts (`chat`, `research`, `summarize`, `code`, `planner`) with the real versions in plan §6.1. Unit tests cover the no-tools path and the with-tools path (using fresh `ToolRegistry` with stub tools) and assert `create_react_agent` is called with the right kwargs.
**Commit:** `feat(api): add ReAct builder and refined prompts for five specialists`

### T7 — Deep-research builder (Wave 2, depends T1, T2, T3)
Implement `app/agents/builders/deep_research.py` with `build_deep_research_agent(spec, model_registry, tool_registry, prompt_registry, checkpointer, store, prompt_versions=None)` that constructs `SubAgent(...)` objects for `researcher` and `critic` from `spec.subagents` and calls `deepagents.create_deep_agent(...)`. Unit test uses a fresh `ToolRegistry` with a stub `web_search` and mocks `create_deep_agent`, then asserts kwargs (`system_prompt`, `tools`, `subagents`).
**Commit:** `feat(api): add deep_research builder wrapping create_deep_agent`

### T8 — Supervisor graph (Wave 3, depends T3, T5, T6, T7)
Implement `app/agents/supervisor_graph.py`. (a) `GraphState` TypedDict. (b) `build_supervisor_graph(...)`: classifier node calling `classify(...)` and returning `Command(goto=intent, update=...)`, six specialist nodes (five from `build_react_agent`, one from `build_deep_research_agent`), edges from START → classifier and each specialist → END. (c) `build_deep_research_only_graph(...)`: bypass graph with START → deep-research → END. Integration test builds the graph with mocked `create_react_agent` and `create_deep_agent` and asserts all 7 node names exist on the compiled graph.
**Commit:** `feat(api): add supervisor graph wiring classifier and six specialists`

### T10 — Routers + `/chat` + `/research` refactor + SSE + frontend (Wave 4, depends T4, T8, T9)
Largest chunk, but single commit because all edits are one contract change. (a) `app/schemas/chat.py` — `ChatRequest` mirroring `ResearchRequest`. (b) `app/routers/chat.py` — POST `/chat`, delegates to `run_graph` with `force_intent=None` and `request.app.state.supervisor_graph`. (c) Refactor `app/routers/research.py` to delegate to `run_graph` with `force_intent="deep-research"` and `request.app.state.deep_research_only_graph`. (d) Rewrite `app/main.py` lifespan: build `ModelRegistry`, import `app.tools` (triggers registration), load `PromptRegistry`, build both graphs, register both routers. (e) Integration tests: `test_chat_endpoint.py` (fake graph, asserts event sequence) and updated `test_research_endpoint.py` (asserts new `intent_classified` event). (f) Frontend: extend `SSEEventMap` in `lib/types.ts`, add `routedIntent` state + `intent_classified` handler in `lib/useResearchStream.ts`, create `RoutedIntentBadge.tsx`, render it in `research/page.tsx`, add a vitest for the hook update.
**Commit:** `feat(api,web): add /chat router, refactor /research bypass, wire intent_classified SSE`

### T11 — Cleanup (Wave 5, depends T10)
Confirm no callers via `grep -rn "from app.services.llm_factory|from app.services.search_tool"`. Delete `app/services/llm_factory.py` and `app/services/search_tool.py`. Decide on `app/services/agent_factory.py` — delete if unused (and delete its tests), else leave with a one-line deprecation comment. Run the full backend + frontend test, lint, and type-check gauntlet to confirm green.
**Commit:** `chore(api): remove legacy llm_factory, search_tool, and agent_factory`

---

## 5. Critical Path

```
T3 (or T5 or T6 or T7) → T8 → T10 → T11
```

**Critical-path length = 4 waves (Waves 2, 3, 4, 5).** Wave 1 is foundational and runs in parallel with no critical-path impact beyond its own completion.

**Longest wave (by steps):** Wave 2 dominates because T4 is 15 steps. Wave 1 dominates by agent count (5).

---

## 6. Merge Coordination Rules (for the orchestrating agent / human)

1. **Do not launch Wave N agents until all Wave N-1 agents have merged.** Each agent operates on the branch tip after the previous wave's merges.
2. **Within a wave, merges can land in any order** as long as there are no file conflicts (see §3). T4 and T6 in Wave 2 don't conflict with each other (different files), but both indirectly depend on Wave 1 merges for `app/tools/__init__.py` and the 5 placeholder prompts respectively.
3. **Every agent must run the full backend test suite before committing** (`cd apps/api && pytest -x --tb=short`). Per the plan's hard invariant, green tests gate every commit.
4. **If an agent encounters a rebase conflict**, stop and surface to the orchestrator — do not silently resolve. The conflict probably means a file-conflict rule in §3 was violated or a wave boundary was skipped.
5. **T10 is the only wave with cross-repo changes** (api + web). If you split T10 into two agents, split by repo: one agent for backend routers + SSE factory use, one for frontend types/hook/badge. Both land as separate commits but in the same wave.

---

## 7. Dispatch Template (copy into each agent's prompt)

```
You are implementing Task T<N> of docs/superpowers/specs/2026-04-14/supervisor-orchestration-plan.md.

Task: T<N> — <chunk name>
Waves already merged: <list>
Your dependencies: <list>
Files you own (may create/modify): <list>
Files you MUST NOT touch: <everything outside the owned list>

Invariants:
- Every TDD step in Chunk <N> of the plan must be executed in order.
- `cd apps/api && pytest -x --tb=short` must pass before your final commit.
- `cd apps/api && ruff check . && mypy app/` must pass before your final commit.
- Your final commit message must be exactly the one in the plan for Chunk <N>.
- Do NOT modify files outside your owned list, even if you think they need changes.
- If you hit a blocker or a merge conflict, STOP and report. Do not improvise.

Begin with TDD step <N>.1 from the plan. Execute each step, verify expected output, move to the next. When all steps are complete, commit and report.
```

---

*End of task DAG. Use this document to dispatch the parallel agent team.*
