# Claude Code Agent Teams in This Codebase — Vetted Research Output

> **Produced by**: a three-teammate Claude Code Agent Team (research-team) operating in parallel:
> **Researcher** (fact-gathering), **Analyst** (synthesis), **Critic** (adversarial review).
> The document went through a **two-pass refinement loop**: Critic flagged factual errors in the initial research and analysis; Researcher re-verified via live commands, Analyst re-integrated; Critic re-critiqued. This version reflects the post-refinement consensus plus the remaining unresolved gaps.
>
> **Date**: 2026-04-14
> **Primary source**: `docs/claude-code-agent-teams-reference.md` + Claude Code agent teams documentation + codebase inspection
> **Working copy audience**: senior engineer deciding whether to adopt agent teams for this codebase

---

## 1. Executive Summary

Claude Code Agent Teams is an **experimental feature** (v2.1.32+) that lets multiple independent Claude Code sessions coordinate on a shared task list and message each other directly. It operates at the **developer-tooling layer** — not the application runtime.

**This repo already runs Claude Code 2.1.105 and has tmux 3.6a installed.** The experimental flag is not set; there are five concrete prerequisites to clear before coding-team work, but read-only review teams can be used immediately once the flag is added.

**The headline recommendation:** Start with a **PR-review team** (read-only, 3 teammates + lead, low blast radius) to validate the tooling and team ergonomics on this codebase *before* attempting a coding team. Then address the five prerequisites before graduating to coding or test-writing teams.

**Repo-specific twist:** Two agent systems already coexist here —
- **Deep Agents** (LangChain/LangGraph) runs inside the FastAPI app as part of user-facing request handling (`apps/api/app/services/agent_factory.py`).
- **Claude Code Agent Teams** runs at the CLI layer for the developer.

They are orthogonal. A Claude Code teammate can **edit** `agent_factory.py` but never **becomes** a Deep Agents subagent at runtime. Conflating the two layers is the most likely onboarding mistake.

---

## 2. Environment State (Verified via live commands)

| Check | Result | Status |
| :---- | :----- | :----- |
| `claude --version` | 2.1.105 | ✓ Above 2.1.32 minimum |
| `which tmux` | /opt/homebrew/bin/tmux (3.6a) | ✓ Split-pane mode supported |
| `.claude/settings.json` has `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | Absent | ✗ Must add to enable |
| `.claude/settings.local.json` has the flag | Absent | ✗ |
| Root `CLAUDE.md` | Does not exist | ✗ Prerequisite for coding teams |
| `.claude/agents/coding.md` `model:` field | `sonet` (typo of `sonnet`) | ✗ Fix before use |
| `.claude/agents/test-runner.md` constraints | Explicitly forbids modifying test files (L94) and source code (L96) | ⚠ Not usable for test *writing* |
| `.claude/agents/test-runner.md` memory path | Previously pointed to a foreign repository; now fixed to this project's path | ✓ Fixed |
| `.claude/hooks/post_buzz.py` | Standalone CLI script (not a lifecycle hook); contains plaintext OpenAI key (L21) and Slack token (L78) | ✗ Security issue + misidentified in early research |
| `.claude/hooks/validate-buzz-commands.sh` | Real `PreToolUse` hook; blocks all Bash except buzz/Slack/read-only git | ⚠ Scope globally-vs-skill-only unconfirmed — could block pytest for teammates |
| `.claude/settings.local.json` permissions | 40+ `allow` entries, many absolute paths into a *different* repo | ⚠ Teammates inherit; audit before spawning |

---

## 3. Prerequisites Before Enabling Agent Teams

Blockers (not optional) for coding team work. Review teams can skip items 1, 2 if spawned read-only.

### 3.1 Enable the experimental flag
Add to `.claude/settings.json`:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### 3.2 Create root `CLAUDE.md`
Without a root `CLAUDE.md`, coding teammates have no architecture awareness. Bare `HTTPException`, wrong layer placement, missing `async def`, skipped soft-delete filters — all become silent regressions.

Minimum content: reference `.claude/rules/architecture.md` and `.claude/rules/guidelines.md`.

### 3.3 Fix `coding.md` model typo
`.claude/agents/coding.md` line 4: `model: sonet` → `model: sonnet`.
Unknown whether this silently falls back to a default or errors — either way, fix before using.

### 3.4 Clarify `validate-buzz-commands.sh` scope
`.claude/settings.json`'s `bash_patterns` already auto-approves `pytest`, `python`, `python3`. **If** `validate-buzz-commands.sh` fires only during buzz-skill invocations, no additional hook work is needed. **If** it fires globally, it overrides `bash_patterns` and blocks all teammate dev tool use.

Trace the hook binding in `settings.json` and resolve before any coding team session.

### 3.5 Move hardcoded credentials out of `post_buzz.py`
Lines 21 (OpenAI key, `sk-proj-…`) and 78 (Slack bot token, `xoxb-…`) are plaintext. Any teammate that grep's `.claude/hooks/` for context harvests them. Move to environment variables.

### 3.6 (Optional but recommended) Audit `settings.local.json`
Previously contained foreign-project `allow` entries that teammates would inherit; those have been removed. Audit before spawning if new entries accumulate.

---

## 4. When to Reach for an Agent Team

**Team test** — before spawning, ask in order:

1. Is there parallel work that would genuinely happen simultaneously? If no → single session.
2. Do workers need to *talk to each other* (challenge findings, share partial results mid-stream)? If no → subagents.
3. Do workers have **distinct** file ownership? If no → redesign the task partition or serialize.
4. Are the prerequisites in §3 satisfied for the work type (read-only review vs. coding)? If no → fix first.

Only if all four answers are yes: spawn a team.

**Break-even heuristic (rough, not derived):** teams earn their 8–15× token cost when work genuinely parallelizes **and** tasks are large enough that spawn/brief/sync overhead (~5–10 min per teammate) is small relative to the work. Tasks under ~30 min of sequential work usually don't break even.

---

## 5. Recommended Use Cases (Vetted)

Ordered by readiness and risk. Do not skip Case 1.

### Case 1 — Parallel PR Review on Streaming Pipeline *(START HERE; lowest risk)*

**Surface**: PRs touching `chunk_mapper.py`, `events.py`, `routers/research.py`.

**Team**: 3 review teammates + lead.
- **Security reviewer**: SSE injection via `content`, `thread_id` validation, `prompt_versions` override abuse in `ResearchRequest` (any user can override production prompts).
- **Streaming correctness reviewer**: event ordering guarantees, `subagent_started`/`subagent_completed` pairing, compression detection edge cases in `_handle_values_snapshot`.
- **Test coverage reviewer**: `_as_list()` channel-wrapper edge cases, compression threshold boundary tests.

**Why first**: read-only, no CLAUDE.md dependency, not blocked by `validate-buzz-commands.sh`, zero file write risk. Validates the tooling before introducing coding complexity.

**⚠ Reviewer permission trap**: reviewers inherit the lead's Write/Edit permissions. Constrain via spawn prompt ("read-only; use Grep/Read/Glob only; never invoke Edit/Write") or flip to plan-only mode after spawning. Otherwise a reviewer that "helpfully fixes" what it finds makes changes with no approval gate.

**Why a team over subagents**: lower-latency cross-reviewer signals — the security reviewer can directly notify the test-coverage reviewer about a bypass path. Subagents *could* achieve the same via lead relay; teams just make it faster.

---

### Case 2 — New Deep Agents Subagent Addition *(requires prereqs 3.2–3.5)*

**Surface**: adding e.g. a `summarizer` subagent to the research pipeline.

**Team**: lead (integration + `schemas/research.py`) + 3 coding teammates.
- **Teammate A** — `agent_factory.py`: `SubAgent(name="summarizer", …)` wired into `create_deep_agent()`.
- **Teammate B** — `events.py` + `chunk_mapper.py`: SSE event-handling updates if the new subagent emits novel event shapes.
- **Teammate C** — `tests/`: unit tests for the new detection path in `ChunkMapper._handle_updates()`.

**`task`-tool naming caveat (IMPORTANT)**: the `name == "task"` check at `chunk_mapper.py:135` is the *LangGraph* delegation mechanism inside Deep Agents — it is NOT Claude Code's `Task` tool. Adding a subagent through `agent_factory.py` **does not** introduce a new Claude Code `task` call; all subagent types share the existing detection path. Teammate B should not fork the detection branch. The *collision risk* is a separate scenario: application code accidentally generating an SSE event with `name == "task"`. That's a code-review concern, not a subagent-definition concern. Add a regression test asserting no SSE event has `name == "task"` unless it originates from a LangGraph tool invocation.

---

### Case 3 — Prompt A/B Testing with Live Critic *(requires prereq 3.1; dev env required)*

**Surface**: `PromptRegistry` `prompt_versions` per-request overrides.

**Team**: lead + Evaluator-A + Evaluator-B + Critic (4 total).
- Evaluators send identical test queries using `prompts/main/v1.md` and `prompts/main/v2.md` respectively.
- Each evaluator `SendMessage`s results to Critic when done.
- **Critic spawn prompt must explicitly state**: *"Do not begin comparison until you have received SendMessage results from BOTH Evaluator-A and Evaluator-B. If only one arrives, wait."*

**Critical environment requirement**: target a **dev or staging** API base URL, never production. Test queries become real requests — hitting production during live traffic degrades service. Include the base URL literally in each spawn prompt.

**Don't edit `prompts/active.yaml` directly** — the `PromptRegistry` is a singleton; editing the file affects in-flight requests globally. Use `ResearchRequest.prompt_versions` overrides instead (per-request, isolated).

---

### Case 4 — Bug Investigation with Competing Hypotheses

**Surface**: ambiguous bugs (e.g., "subagent events sometimes missing from SSE stream").

**Team**: lead + 3–4 investigator teammates, each testing a distinct hypothesis read-only:
- H1: `_as_list()` not unwrapping `Add([…])` correctly.
- H2: `tool_call_id` collision across concurrent requests (shared `ChunkMapper` state).
- H3: Deep Agents version bumped `task` tool name.
- H4: Race between `messages` and `updates` stream modes.

Each investigator SendMessage's findings to the lead and to peers. If H2 is confirmed, H1's investigator stops early — short-circuiting saves tokens.

**Only the lead writes the fix.** Investigators are read-only.

---

### Case 5 — Test Suite Expansion *(requires prereqs 3.2–3.3)*

**Surface**: `tests/unit/test_chunk_mapper.py`, `tests/unit/test_prompt_registry.py`, `tests/integration/test_research_endpoint.py`.

**Team**: lead + 3 coding teammates, one owning each test file.

**⚠ Do NOT use `test-runner.md` as the teammate role**: its definition explicitly prohibits modifying test files (L94) and source code (L96), and its memory path is hardcoded to a different repository (L120–121). Use **`coding.md`** (after the `sonet → sonnet` fix) with a test-focused spawn prompt.

**Self-claim caveat**: task titles must name **specific files**. "Add tests for the streaming layer" is ambiguous and can be claimed by two teammates. Write "Add tests for `_as_list()` in `test_chunk_mapper.py`" instead.

**Task-sizing note**: 1 task per teammate here violates the docs' 5–6-per-teammate rule. This is a **deliberate simplicity trade** — zero overlap risk beats efficiency for first coding-team use. Batch more files per teammate (A: chunk_mapper + events) if efficiency matters once the pattern is proven.

---

## 6. Trade-offs

### Teams vs Single Session
| Dimension | Single | Team |
| :-------- | :----- | :--- |
| Token cost | Lowest | 8–15× per coding teammate (full context × N) |
| Sequential dependencies | No overhead | Dead weight — blocked teammates still burn tokens |
| Speed on genuinely parallel work | Serializes | N× faster |
| Architecture enforcement | Full (rules loaded by harness) | None without root CLAUDE.md |
| Recovery from failure | Restart one session | Orphaned teammates need manual cleanup |

### Teams vs Subagents
| Dimension | Subagents | Teams |
| :-------- | :-------- | :---- |
| Communication | Sub → lead (relay possible, slower) | Any ↔ any, direct |
| Cost | Low–medium | High |
| File writes | Sub context isolated | Shared working directory |
| Cross-worker signal | Lead-relayed | Native SendMessage |
| Architecture rules | Inherited from lead | Not guaranteed w/o CLAUDE.md |
| Best for | Focused lookups, verifications | Adversarial review, A/B+critic, parallel coding |

Existing `Explore`, `Plan`, `coding`, `test-runner` subagents should stay subagents for single-shot delegation.

### Teams vs Git Worktrees
| Dimension | Teams | Worktrees |
| :-------- | :---- | :-------- |
| File isolation | Shared — manual partitioning | Fully isolated |
| Cross-worker communication | Native | None (manual) |
| Merge overhead | None (same branch) | Rebase/merge required |
| Long-running parallel branches | Risky | Designed for this |

Use **worktrees** for different-branch parallel work (two competing architectural approaches). Use **teams** for same-branch parallel work (Cases 2 and 5).

---

## 7. Practical Recommendations

### Team sizing

| Task shape | Team size |
| :--------- | :-------- |
| PR review (security + streaming + tests) | 3 + lead |
| Cross-layer feature (3–4 files) | 3 + lead |
| Bug investigation (3–4 hypotheses) | 3–4 + lead |
| Test suite expansion | up to 3 coding teammates |
| Prompt A/B with critique | 2 evaluators + 1 critic + lead |

**Hard ceiling: 5 teammates.** Features in this codebase rarely decompose into more than 4 independent streams; idle teammates burn tokens at full context-window cost.

### Role patterns that work

- **Researcher/Analyst/Critic (read-only)** — safest pattern; zero file-conflict risk; not blocked by `validate-buzz-commands.sh`. Ideal first-team use.
- **Layer-owner (schema-first)** — each teammate owns one layer (`services/` | `streaming/` | `schemas/` | `routers/`). **Caveat**: if Teammate A's work depends on Teammate B's schema, A blocks until B finalizes. Mitigate by **drafting schemas before parallelizing** — lead writes the Pydantic schemas first, then spawns implementers. Never kick off layer-owner teammates with undefined interfaces.
- **Lead coordinates OR implements — not both.** If integration work is substantial, spawn a 4th "integration" teammate for `main.py` / `agent_factory.py`. Lead pure-coordinates: assigns, reviews, synthesizes.
- **Evaluator/Critic** — spawn prompt for Critic must explicitly require both evaluator messages before comparison starts.
- **Test-writer swarm** — `coding.md` teammates (post typo-fix), one file per teammate, specific filenames in task titles.

### Hook configuration (pre-flight before coding teams)

1. **First**: resolve `validate-buzz-commands.sh` scope (§3.4). If globally-scoped, it overrides `bash_patterns` and must be narrowed.
2. **Then (if needed)**: add lifecycle hooks under a `hooks` key in **project-level** `.claude/settings.json` (not `~/.claude/settings.json` which is global). Consult the Claude Code hooks docs for the exact schema before writing. Useful gates:
   - `TaskCompleted` → run pytest; exit 2 if failing to block completion
   - `TaskCreated` → require task descriptions to name specific files (prevents self-claim overlaps)
   - `TeammateIdle` → nudge on stuck pending tasks

Current research has **not** confirmed the exact hook JSON schema — treat the above as conceptual until verified against live docs.

### Anti-patterns to avoid

1. **Coding team before root CLAUDE.md exists** — architecture violations invisible until review.
2. **`test-runner.md` as a test writer** — cannot modify files; memory path points elsewhere.
3. **`coding.md` before fixing `model: sonet`** — unknown fallback behavior.
4. **Under-briefed spawn prompts** — "Add a subagent" without explaining `chunk_mapper.py:130–159` produces correct factory code that silently breaks the stream.
5. **Two teammates touching `agent_factory.py` or `chunk_mapper.py`** — single owner per session.
6. **Schema-less parallelization** — kicking off layer-owner teammates without defined interfaces.
7. **Case 3 against production** — A/B queries are real requests. Dev/staging only.
8. **Broadcast (`to: "*"`) for task-specific signals** — 4-teammate team = 4× cost.
9. **Team work during live user load** — 4 Claude Code teammates + per-user Deep Agents sessions = 7+ concurrent Claude sessions on one key.

---

## 8. Open Risks (Remaining unresolved items)

Items the team could not verify in this pass. Resolve before relying on them.

1. **`validate-buzz-commands.sh` scope** *(most immediate blocker for coding teams)* — globally-scoped or buzz-only? Trace the hook binding in settings.json.
2. **Hardcoded credentials in `post_buzz.py`** — plaintext OpenAI key and Slack token. Move to env vars immediately.
3. **No CLAUDE.md means no architecture enforcement** — most critical gap for coding teams.
4. **`settings.local.json` permissions inheritance** — 40+ `allow` entries with absolute paths to a different repo. Audit before spawning.
5. **`task`-tool SSE collision risk** — regression test missing: assert no SSE event has `name == "task"` unless from LangGraph.
6. **No session resumption for in-process teammates** — lead crash orphans teammates. Commit teammate work at task boundaries, not team completion.
7. **`memory: project` frontmatter behavior in teammate sessions is undocumented** — all three `.claude/agents/` definitions include this field; `test-runner.md`'s hardcoded path to a different repo is concrete evidence this needs verification before use.
8. **SQLite checkpointer boundary** — safe for in-flight Deep Agents sessions (state lives in SQLite, not files), but teammates editing `stores/memory_store.py` affect the next request. Note in spawn prompts for store work.
9. **One team per session** — plan review-team → coding-team sequentially, never in parallel.
10. **Actual Claude Code hook JSON schema** — Critic flagged that the analysis presents hook config conceptually; the exact schema was not verified in this pass. Look it up against live docs before writing real hook config.
11. **What `model: sonet` resolves to** — silent fallback, error, or different model? Spawn a test teammate to confirm.

### Blind spots explicitly acknowledged by the Critic

These are questions the team flagged as out of scope for this pass and still **unanswered**:
- Anthropic API rate limits under 5-teammate parallelism sharing one key.
- Teammate context-window exhaustion behavior mid-task (silent truncation, stall, or error via mailbox).
- Whether `.claude/rules/` files load for teammate sessions (load-bearing for coding teams).

---

## 9. Pre-Enablement Checklist

- [ ] Add `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1"` to `.claude/settings.json`
- [ ] Create root `CLAUDE.md` referencing `.claude/rules/architecture.md` and `.claude/rules/guidelines.md`
- [ ] Fix `model: sonet` → `model: sonnet` in `.claude/agents/coding.md`
- [ ] Move `post_buzz.py` credentials (OpenAI key L21, Slack token L78) to env vars
- [ ] Confirm `validate-buzz-commands.sh` scope (global or buzz-only); narrow if needed
- [ ] Fix `test-runner.md` hardcoded memory path (L120–121) if you intend to use it
- [ ] Audit `.claude/settings.local.json` permissions before first team session
- [ ] **First use**: PR review team (read-only, Case 1) on a real PR
- [ ] After Case 1 succeeds: pick Case 2, 4, or 5 based on next task shape
- [ ] Every task description must name specific files when self-claim is used

---

## 10. Appendix: Methodology

This document was produced by a three-teammate Claude Code agent team operating in parallel:

- **Researcher** (sonnet) — read the reference doc, inspected the codebase, produced a structured inventory of findings.
- **Analyst** (sonnet) — waited for Researcher's trigger message, synthesized findings into actionable use cases and recommendations.
- **Critic** (sonnet) — waited for Researcher's trigger, then critiqued research and (when it arrived) analysis, flagging gaps, unexamined assumptions, pitfalls, and specific improvement suggestions.

**Coordination**: `SendMessage` with file-locked task list. Two refinement rounds occurred — Critic flagged factual errors (e.g., `post_buzz.py` misidentified as a hook; version gate left as open question when `claude --version` could resolve it in one command); Researcher re-verified via live commands; Analyst re-synthesized.

**What worked**: adversarial structure forced verification. Research v1 claimed "hooks infrastructure already exists"; Critic reading the actual files overturned that claim. A single agent would likely have carried the wrong premise forward.

**What would improve next time**: add a `TaskCompleted` hook enforcing pytest on test-writing tasks; require the Researcher to run verification commands (`claude --version`, `which tmux`, listing `.claude/agents/` and `.claude/hooks/`) **before** sending the trigger message, not after being challenged.

---

*End of vetted research output.*
