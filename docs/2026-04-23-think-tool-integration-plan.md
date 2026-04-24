# Plan — Integrate `think_tool` (reflection) into the Deep Research Agent

> Source: Recommendation #1 from `docs/2026-04-23-open-deep-research-analysis.vi.md`.
> Status: Proposed. Needs sign-off before Chunk 1 begins.
> Estimated effort: ~0.5 dev-day, 4 PRs.

## Goal

Add a **no-op reflection tool** called `think_tool` to the main agent and the `researcher` subagent. Update their prompts to call it before and after each search / delegation step. Surface the reflections to the UI as a new SSE event so the dashboard can render "the agent is thinking" explicitly.

## Why

From the ODR analysis:
- `think_tool` forces the model to serialize reasoning into the message log instead of emitting parallel tool calls impulsively.
- Prompt says "use it before/after every search" → the model writes out **what it already knows** and **what gap remains** — reducing redundant searches and producing tighter synthesis.
- Tool is cheap: it just echoes the input string. The value is behavioral, not functional.

Observed today in `chat-agents`: the researcher subagent runs 2-4 searches without a reasoning checkpoint between them; results are often redundant. Main agent's decision to spawn each subagent is prompted in `main/v2.md` but not reinforced with a reasoning artifact the model is forced to produce.

## Non-goals

- **Not** rewriting the graph. Still `create_deep_agent(...)` with 2 subagents.
- **Not** adding parallelism (that's recommendation #2 + #7 — separate plan).
- **Not** flipping `active.yaml` to the new prompt versions in the same PR that introduces them. A/B via `prompt_versions` request override first.
- **Not** introducing structured output for reflections (plain string is sufficient).

---

## Decisions (confirmed 2026-04-23)

| # | Question | Decision | Note |
|---|---|---|---|
| D1 | Where does `think_tool` live? | ✅ **`apps/api/app/tools/think_tool.py`** | `app/tools/` already exists as an empty module. Confirmed by user. Populates the folder that was scaffolded for this purpose. |
| D2 | Which agents get it? | ✅ **Main + researcher** | Critic keeps `tools=[]` — it reviews, doesn't search. Confirmed by user. |
| D3 | New SSE event? | ✅ **Yes: `reflection_logged`** with `{role, reflection}` payload | Gives the dashboard a first-class timeline surface for agent reasoning. Confirmed by user. |
| D4 | Bump prompt versions or overwrite? | ✅ Bump: new `main/v3.md`, `researcher/v2.md`. `active.yaml` unchanged until Chunk 4. | CLAUDE.md rule: *"Never edit an existing `prompts/<name>/vN.md` — add a new version and update `active.yaml`."* |
| D5 | Does `think_tool` return the input verbatim, or a structured summary? | ✅ Verbatim echo | Simplest. Matches ODR. |
| D6 | Max reflections per run? | ✅ Soft limit via prompt only | No enforced cap in v1. Revisit if call counts blow up during Chunk 4 validation. |

---

## File plan

| File | Change | Owner |
|---|---|---|
| `apps/api/app/tools/__init__.py` | **NEW** — empty init (package marker) | Chunk 1 |
| `apps/api/app/tools/think_tool.py` | **NEW** — `@tool` wrapper, ~15 lines | Chunk 1 |
| `apps/api/app/services/agent_factory.py` | Import from `app.tools.think_tool`; add to main + researcher `tools=[...]` | Chunk 1 |
| `apps/api/prompts/main/v3.md` | **NEW** — copy v2, insert think_tool usage rules | Chunk 1 |
| `apps/api/prompts/researcher/v2.md` | **NEW** — copy v1, insert think_tool usage rules | Chunk 1 |
| `apps/api/tests/unit/test_think_tool.py` | **NEW** — tool contract tests | Chunk 1 |
| `apps/api/tests/integration/test_agent_factory.py` | Assert `think_tool` registered on main + researcher | Chunk 1 |
| `apps/api/app/streaming/events.py` | Add `reflection_logged()` factory | Chunk 2 |
| `apps/api/app/streaming/chunk_mapper.py` | Detect `think_tool` tool_calls → emit event | Chunk 2 |
| `apps/api/tests/unit/test_events.py` | Assert new event shape | Chunk 2 |
| `apps/api/tests/unit/test_chunk_mapper.py` | Add case: think_tool tool_call → `reflection_logged` | Chunk 2 |
| `apps/web/lib/types.ts` | Add `reflection_logged` to `SSEEventMap` | Chunk 3 |
| `apps/web/lib/useResearchStream.ts` | Accumulate reflections in hook state | Chunk 3 |
| `apps/web/lib/useResearchStream.test.ts` | Hook emits reflection on event | Chunk 3 |
| `apps/web/app/research/components/ReflectionPanel.tsx` | **NEW** — renders reflection timeline | Chunk 3 |
| `apps/web/app/research/page.tsx` | Mount `ReflectionPanel` in layout | Chunk 3 |
| `apps/api/prompts/active.yaml` | Flip `main: v3`, `researcher: v2` after validation | Chunk 4 |

---

## Chunks

Each chunk is a landable PR with its own tests.

### Chunk 1 — Backend tool + prompt versions *(no UI impact, silent behavior change)*

**Testable after:** `pytest` green; agent instantiates with `think_tool` bound; manual curl of `/research` with `prompt_versions={"main":"v3","researcher":"v2"}` shows think_tool calls in logs.

- [ ] **1.1a** Create `apps/api/app/tools/__init__.py` (empty — package marker). Note: the directory already exists but contains only `__pycache__`, so Python currently treats it as a namespace package; adding `__init__.py` makes it a regular package and imports cleaner.
- [ ] **1.1b** Create `apps/api/app/tools/think_tool.py`:
    ```python
    from langchain_core.tools import tool

    @tool
    def think_tool(reflection: str) -> str:
        """Reflect on research progress and identify gaps before the next step.

        Call this BEFORE starting a new search to state what you already know
        and what gap this search will close. Call it AFTER a batch of searches
        to summarize findings and decide whether to search more or conclude.

        The tool simply echoes your reflection. Its purpose is to force you
        to serialize reasoning into the message log rather than emitting
        parallel tool calls impulsively.
        """
        return f"Reflection recorded: {reflection}"
    ```
- [ ] **1.2** Wire into `agent_factory.py`:
    - Import: `from app.tools.think_tool import think_tool`.
    - Add `think_tool` to `tools=[internet_search, think_tool]` in `create_deep_agent(...)`.
    - Add `think_tool` to `tools=[internet_search, think_tool]` in the researcher `SubAgent`.
    - Critic `SubAgent` unchanged (its `tools=[]` stays).
- [ ] **1.3** Create `apps/api/prompts/main/v3.md` — copy v2 verbatim, then:
    - At the top, add: *"Before **each** `researcher` subagent spawn, call `think_tool` with a 1-2 sentence statement of what gap that subagent will close. After the subagent returns, call `think_tool` again to note what was found and whether the next planned topic is still relevant or should be adjusted."*
    - Near the draft-report step, add: *"Before writing `draft.md`, call `think_tool` to list any unanswered sub-questions from the todo list. If any remain, spawn another researcher before drafting."*
- [ ] **1.4** Create `apps/api/prompts/researcher/v2.md` — copy v1 verbatim, then prepend:
    - *"For every search you plan to run: first call `think_tool` with (a) what you already know from prior searches, (b) the specific fact this next search must produce. After the search returns: call `think_tool` again with 1-2 sentences on whether the gap was closed. Stop searching as soon as you have 3 independent, relevant sources — do not pad for completeness."*
- [ ] **1.5** Add `apps/api/tests/unit/test_think_tool.py`:
    - Assert `think_tool.name == "think_tool"`.
    - Assert docstring contains the reflection guidance.
    - Assert `think_tool.invoke({"reflection": "x"})` returns a string containing `"x"`.
- [ ] **1.6** Update `apps/api/tests/integration/test_agent_factory.py`:
    - Assert `think_tool` appears in the main agent's bound tool list.
    - Assert `think_tool` appears in the researcher subagent's tool list.
    - Assert it does **not** appear in the critic subagent.
- [ ] **1.7** Run `ruff check . && mypy app/ && pytest`. Commit:
    > `feat(api): add think_tool for reflective research loops`

### Chunk 2 — SSE contract extension *(backend surface, safely additive)*

**Testable after:** `pytest` green; `chunk_mapper` test shows `reflection_logged` emitted for synthetic `think_tool` tool_call; frontend ignores unknown event type gracefully (existing parser contract).

- [ ] **2.1** Add to `apps/api/app/streaming/events.py`:
    ```python
    def reflection_logged(role: Literal["main", "researcher"], reflection: str) -> dict:
        return _sse("reflection_logged", {"role": role, "reflection": reflection[:2000]})
    ```
    Truncate at 2000 chars — reflections are short by design; long ones are a model misuse signal.
- [ ] **2.2** Extend `chunk_mapper._handle_updates()`:
    - When iterating `_as_list(update.get("messages"))`, for each `tool_call` with `name == "think_tool"`:
        - Extract `args["reflection"]`.
        - Infer `role`: if the surrounding update key is a subagent name (node in the researcher subgraph — detect by presence of `"researcher"` in the node path), role = `"researcher"`; else `"main"`.
        - Emit `events.reflection_logged(role, reflection)`.
    - Dedupe by `tool_call["id"]` across chunks (similar to `_active_subagents`).
- [ ] **2.3** Add `apps/api/tests/unit/test_events.py` case asserting `reflection_logged` payload shape.
- [ ] **2.4** Add `apps/api/tests/unit/test_chunk_mapper.py` cases:
    - tool_call `name=think_tool` on main-level message → emits `{role:"main", reflection:"..."}`.
    - Same tool_call_id seen twice → emitted once.
    - tool_call `name=internet_search` → does **not** emit reflection event.
- [ ] **2.5** `ruff check . && mypy app/ && pytest`. Commit:
    > `feat(api): emit reflection_logged SSE events for think_tool calls`

### Chunk 3 — Frontend plumbing *(UI surface)*

**Testable after:** `npm test` green; `npm run dev` shows reflections accumulating in a dedicated panel during a real run.

- [ ] **3.1** Extend `apps/web/lib/types.ts`:
    - Add `reflection_logged: { role: "main" | "researcher"; reflection: string }` to `SSEEventMap`.
    - Add `Reflection = { role: ...; reflection: string; at: number }` type.
- [ ] **3.2** Extend `apps/web/lib/useResearchStream.ts`:
    - Add `reflections: Reflection[]` to state.
    - On `reflection_logged`: append `{ ...data, at: Date.now() }`.
    - Reset on `stream_start`.
- [ ] **3.3** Update `apps/web/lib/useResearchStream.test.ts` with one new case:
    - Feed a synthetic SSE frame of type `reflection_logged`.
    - Assert hook state includes the reflection in order.
- [ ] **3.4** Create `apps/web/app/research/components/ReflectionPanel.tsx`:
    - Props: `reflections: Reflection[]`.
    - Render a vertical timeline, one item per reflection. Badge the role (`main` = slate, `researcher` = indigo). Show the text in `prose prose-sm` below the badge.
    - Empty state: a muted line *"Reflections will appear as the agent reasons about gaps."*
- [ ] **3.5** Mount the panel in `apps/web/app/research/page.tsx` next to the transcript (or below subagents — designer's call). Pass `reflections` from the hook.
- [ ] **3.6** `npm run lint && npm test && npm run build`. Manual dev-server check for UX. Commit:
    > `feat(web): render reflection_logged stream as a timeline`

### Chunk 4 — Promote to default *(after validation)*

**Testable after:** Diff 5-10 sample questions against the v2/v1 baseline with the prompt-version override; compare number of searches, report length, citation count. Only proceed if the new versions are ≥ baseline quality.

- [ ] **4.1** Run a small A/B by hitting `/research` twice per sample question:
    - Baseline: `prompt_versions={"main":"v2","researcher":"v1"}`.
    - Candidate: `prompt_versions={"main":"v3","researcher":"v2"}`.
    - For each: count tool_calls by type (think_tool, internet_search, task), report length, distinct citation count.
    - Capture results in a short note under `docs/`.
- [ ] **4.2** If candidate wins (fewer redundant searches AND report quality preserved/better):
    - Update `apps/api/prompts/active.yaml`:
      ```yaml
      main: v3
      researcher: v2
      critic: v1
      ```
    - Commit: `chore(prompts): promote v3 main + v2 researcher with think_tool`.
- [ ] **4.3** If candidate loses: keep new versions in the registry but leave `active.yaml` pointing at `v2`/`v1`. File a follow-up to iterate on the prompt wording. No revert needed — file-backed registry means nothing is orphaned.

---

## Validation plan

A one-off eval harness is **out of scope** for this plan (that's recommendation #6). For Chunk 4 we'll do an ad-hoc manual comparison on `docs/sample-research-questions.txt`. If ambiguous, keep `active.yaml` unchanged and revisit after the eval harness ships.

Minimum signals to watch during Chunk 4:
- **Search count per run** should drop 10-30% with `think_tool` in play.
- **`think_tool` call count** should roughly equal `2 × (subagent_spawns + researcher_searches)` (call before + after). If it's ~0, the prompt isn't landing.
- **Report length & citation count** should not regress.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Model ignores `think_tool` despite prompt — no behavior change. | If D6 becomes a problem, add a wrapper that raises a `ToolException` if a search runs without a preceding `think_tool` call in the same turn. Keep as follow-up, not in v1. |
| Reflections bloat the stream (model over-uses the tool). | 2000-char truncation in `reflection_logged()`. Monitor for noise; tighten to 1000 if needed. |
| Subagent-role detection in chunk_mapper is fragile. | Fallback to `"main"` when unknown. Add a unit test covering the "unknown node" case. Role is UX polish, not correctness-critical. |
| `deepagents` upgrade changes how tools propagate to subagents. | Integration test in **1.6** asserts the binding. Will fail loudly on upgrade. |
| Prompt changes change behavior for users who explicitly request `v2`/`v1`. | They won't — old versions remain in `prompts/*/v*.md`. Registry is additive. |

## Rollback

- Chunks 1-3 are additive: revert by deleting new files + reverting `agent_factory.py` changes. No migration needed.
- Chunk 4 rollback: revert `active.yaml` to `{main: v2, researcher: v1, critic: v1}`. Done.

## Out-of-scope (future work)

- Enforced cap on `think_tool` calls (D6).
- Structured reflection schema (e.g. `{known: str, gap: str}`).
- Surfacing reflections in the final report as an "agent reasoning appendix".
- Applying the same pattern to the critic subagent (different tool set would be needed).

---

*Drafted 2026-04-23 alongside the ODR analysis. Ready for review.*
