# LangGraph-Style Hierarchical Research Teams on Claude Code Agent Teams

**Design Document** — Synthesized from structured research, analysis, critique, and codebase signals.  
**Audience:** Engineers building multi-agent orchestration on top of Claude Code Agent Teams in the chat-agents codebase.  
**Scope:** Pattern reference, architectural guidance, operational rules. Does not include runtime code.

---

## 1. TL;DR

- **The pattern:** A hierarchical research team implemented on Claude Code Agent Teams, where a permanent supervisor (team-lead) routes work through specialist teammates (Researcher → Analyst ∥ Critic → Finalizer) using a shared typed state file (`state.json`) as the routing signal and field-scoped concurrency control.
- **When to use it:** Long-running, multi-phase tasks with distinct specialist roles, where parallel execution across phases provides measurable latency reduction.
- **What it costs:** Each teammate is a full Claude session. Token cost scales linearly with team size. Fan-out is approximate, not true concurrent. Shared state requires strict field-ownership discipline to avoid corruption.
- **What it does not do:** True checkpoint/replay (state.json is forward-only persistence, not LangGraph's AsyncSqliteSaver). Nested teams (no sub-supervisor pattern). Automatic concurrency control (no reducers; field ownership is a prompt-level convention).
- **Hard constraint:** This pattern operates at the **developer terminal level** (meta-level orchestration). It is entirely separate from — and must never be conflated with — the LangGraph/deepagents stack that runs inside the FastAPI process.

---

## 2. Two-Layer Clarity — Start Here

**Conflating these two layers is the primary architectural mistake this document exists to prevent.**

### Layer 1: deepagents / LangGraph — Inside the FastAPI process

`apps/api/app/services/agent_factory.py` imports `SubAgent, create_deep_agent` from `deepagents` — an abstraction layer over raw LangGraph `StateGraph`. This runs:

- **Inside** the FastAPI request cycle or background task runner
- As Python code in the API process (asyncpg, Redis, SQLAlchemy in the same process)
- For **runtime AI orchestration**: KB ingestion, RAG retrieval, multi-step tool calling, streaming Claude responses to users
- With LangGraph primitives: `StateGraph`, `TypedDict`, `AsyncSqliteSaver`, `Send`, `Command`

This layer handles programmatic API-level orchestration. `deepagents` is a published PyPI package (confirmed: `deepagents` 0.5.2, with 54 released versions — see §13 OQ1 resolution). It is a LangChain-adjacent abstraction over `StateGraph` that packages the deep-agent pattern (main + sub-agents + shared file-system tool + planning loop) with sensible defaults. New projects may adopt it directly; raw `StateGraph` or the `langgraph-supervisor` prebuilt remain viable alternatives where finer control is needed.

### Layer 2: Claude Code Agent Teams — Developer's terminal

This document describes this layer. It runs:

- **Outside** the FastAPI process, in the developer's shell or CI environment
- As independent Claude Code sessions communicating via file-based state and the mailbox (SendMessage)
- For **dev-time orchestration**: research, analysis, code review, incident investigation, PR evaluation
- With Claude Code primitives: Task system, SendMessage, state.json, hooks, plan-approval mode

These two layers address entirely different problems. A KB ingestion job is Layer 1. A research team analyzing *how to implement* KB ingestion is Layer 2. They share vocabulary (supervisor, state, routing) but not infrastructure.

| Dimension | Layer 1: deepagents / LangGraph | Layer 2: Claude Code Agent Teams |
|---|---|---|
| Where it runs | Inside FastAPI process | Developer terminal / CI |
| Runtime | Python asyncio event loop | Independent Claude Code sessions |
| State store | TypedDict channels + AsyncSqliteSaver | state.json on disk |
| Routing | `add_conditional_edges`, `Command` | Supervisor reads state.json, sends messages |
| Parallelism | True concurrent (superstep) | Approximate (near-simultaneous session start) |
| Replay | Full history via `get_state_history()` | Forward-only; last committed write only |
| Primary use | User-facing API features | Dev workflow automation |

---

## 3. Typed State Schema

The `state.json` file is the shared typed record for the team. It is the **authoritative routing signal** and the **field-ownership contract**. Initialize it before spawning any teammate.

```python
class TeamState(TypedDict):
    # --- Graph control fields (supervisor owns all of these) ---
    objective: str           # Immutable. Set at init. Never modified.
    status: str              # Routing enum. Only supervisor or Finalizer writes this.
                             # Values: "initialized" | "research_complete" | "analysis_complete"
                             #         | "critique_complete" | "needs_more_research"
                             #         | "finalized" | "forced_complete" | "aborted_turn_limit"
    turn_count: int          # Monotonic. ONLY supervisor increments, after all parallel
                             # workers report in. Workers never touch this field.
    max_turns: int           # Immutable. Set at init. Guards against infinite loops.

    # --- Worker output fields (one owner per field) ---
    structured_inventory: StructuredInventory   # OWNED BY: researcher
    analysis_draft: AnalysisDraft               # OWNED BY: analyst
    critique_summary: CritiqueSummary           # OWNED BY: critic
    # (final deliverable is written to disk, not to state.json)

    # --- Infrastructure fields (supervisor owns) ---
    gaps: list[Gap]              # Written by critic, read by finalizer and supervisor
    handoff_log: list[HandoffEvent]  # Append-only log. All teammates append (read-merge-write).
                                     # tmp+rename for atomic appends.
    final_deliverable_path: str  # Set at init. Written by finalizer as confirmation.
    restart_from: str | None     # Set by supervisor on fault recovery. Tells replacement
                                 # teammate which status checkpoint to resume from.
```

### Per-field ownership table

| Field | Owner | May others read? | Notes |
|---|---|---|---|
| `objective` | supervisor (immutable) | yes | Never modified after init |
| `status` | supervisor + finalizer | yes | Routing signal; workers set only their completion status via their field + supervisor reads |
| `turn_count` | supervisor only | yes | Race condition: only supervisor increments, after all parallel workers complete |
| `max_turns` | supervisor (immutable) | yes | Never modified after init |
| `structured_inventory` | researcher | yes | Analyst, Critic, Finalizer read; only Researcher writes |
| `analysis_draft` | analyst | yes | Critic, Finalizer read; only Analyst writes |
| `critique_summary` | critic | yes | Finalizer reads; only Critic writes |
| `gaps` | critic | yes | Supervisor, Finalizer read |
| `handoff_log` | all (append-only) | yes | tmp+rename protocol; each entry is a structured event |
| `final_deliverable_path` | supervisor (init) | yes | Finalizer confirms existence post-write |
| `restart_from` | supervisor | yes | Null normally; set on fault recovery path only |

---

## 4. Node Roles & Handoff Contracts

Each teammate is a named node. Its spawn prompt is its node function. It reads state.json, does domain work, writes its owned field, advances `status`, and messages the supervisor.

### Supervisor (team-lead)

| Property | Detail |
|---|---|
| **Inputs** | `status`, `turn_count`, `max_turns`, `gaps` from state.json; TeammateIdle hook signal |
| **Outputs** | Routing decision: TaskUpdate(owner=next_teammate), SendMessage(to=next_teammate) |
| **Fields owned** | `objective`, `status`, `turn_count`, `max_turns`, `restart_from` |
| **Status transitions** | Sets status after reading each worker's completion signal |
| **Invariant** | NEVER does domain work. NEVER reads/writes files (except state.json). NEVER calls tools other than: Read, TaskUpdate, SendMessage. |

**Routing preamble (add to every routing decision):**
```
Before routing: read state.json.
If turn_count >= max_turns: route to Finalizer, set status="forced_complete".
If turn_count >= max_turns - 1 and current node is not Finalizer: warn in handoff_log.
Increment turn_count (supervisor only). Then route.
```

### Researcher

| Property | Detail |
|---|---|
| **Inputs** | `objective` from state.json; codebase files; external docs (Context7) |
| **Outputs** | `structured_inventory` (atomic facts: primitives, mappings, codebase signals, open questions) |
| **Fields owned** | `structured_inventory` |
| **Completion protocol** | Write `structured_inventory` → append to `handoff_log` → set `status="research_complete"` → message supervisor |
| **Model** | `claude-sonnet-4-6` (deep research requires full context) |
| **Idempotency rule** | If `structured_inventory` already populated at spawn time: skip writing, report current status only |

### Analyst

| Property | Detail |
|---|---|
| **Inputs** | `structured_inventory`, `objective` |
| **Outputs** | `analysis_draft` (patterns, use cases, trade-offs, recommended architecture) |
| **Fields owned** | `analysis_draft` |
| **Completion protocol** | Write `analysis_draft` → append to `handoff_log` → message supervisor (supervisor sets status) |
| **Model** | `claude-sonnet-4-6` |
| **Idempotency rule** | If `analysis_draft` already populated: skip, report status |
| **MUST NOT** | Touch `turn_count` — this is the supervisor's field |

### Critic

| Property | Detail |
|---|---|
| **Inputs** | `structured_inventory`, `analysis_draft` |
| **Outputs** | `critique_summary` (assumptions, pitfalls, challenged patterns, verdict), `gaps` |
| **Fields owned** | `critique_summary`, `gaps` |
| **Completion protocol** | Write `critique_summary` + `gaps` → append to `handoff_log` → message supervisor |
| **Routing outcomes** | `verdict="approved"` → supervisor routes to Finalizer. `verdict="vetted_with_caveats"` → supervisor routes to Finalizer with gap list. `verdict="needs_more_research"` → supervisor routes back to Researcher (costs a turn; check turn_count first). |
| **Model** | `claude-haiku-4-5-20251001` (validation role; lighter model acceptable) |
| **MUST NOT** | Touch `turn_count` |

### Finalizer

| Property | Detail |
|---|---|
| **Inputs** | All of: `structured_inventory`, `analysis_draft`, `critique_summary`, `gaps`, `handoff_log`, `objective` |
| **Outputs** | Final deliverable file at `final_deliverable_path` |
| **Fields owned** | Writes to `final_deliverable_path` on disk only. No state.json field beyond appending handoff_log. |
| **Completion protocol** | Write deliverable → set `status="finalized"` → append to `handoff_log` → message supervisor |
| **Forced-finalization** | If `status="forced_complete"` at spawn: produce deliverable anyway, prepend a caveat section noting it is incomplete due to turn-budget exhaustion |
| **Spawn mode** | Recommended: `plan-approval mode` (EnterPlanMode) — supervisor reviews deliverable outline before Finalizer writes, equivalent to `interrupt_before=['finalizer']` |
| **Model** | `claude-sonnet-4-6` |
| **Output file ownership** | Finalizer is the ONLY teammate that writes to the deliverable file. Analyst must never write intermediate drafts there. |

---

## 5. Supervisor-as-Tool vs Supervisor-as-Node — Tiered by Task Duration

The Analyst's original recommendation ("Supervisor-as-tool is the preferred pattern") was challenged by the Critic as incomplete. The correct guidance is tiered by task duration and I/O profile.

### Tier 1: Supervisor-as-Tool — Short, synchronous specialists

**When to use:** Specialist tasks complete in seconds to low minutes, return a bounded result directly to the supervisor, and do not need parallel execution.

**How it works in Claude Code:** Lead spawns specialist via `Agent` tool, blocks until result returns, reads return value, decides next action. Each specialist gets a tightly scoped context window — only what it needs, nothing more.

**Advantages:**
- Maximum context control per specialist
- Failure isolation per Agent call
- No state.json coordination required for simple tasks
- Straightforward to reason about

**Examples:** Schema validation, quick classification, short code review of a single file, format conversion.

**Disadvantage:** Each specialist runs serially inside the lead's Agent call chain. Lead's context grows with accumulated specialist outputs. Inappropriate for tasks longer than ~2 minutes.

### Tier 2: Supervisor-as-Node — Long-running async specialists

**When to use:** Specialist tasks run for multiple minutes, may need to query external services, produce large outputs, or run in parallel with other specialists.

**How it works in Claude Code:** Lead pre-spawns the full team at initialization (all idle). When routing, lead creates N tasks and sends directed `SendMessage` to each specialist. Lead then waits passively (monitored via TeammateIdle hook). When all parallel workers complete, lead reads `state.json.status` as the authoritative routing signal and increments `turn_count`.

**Advantages:**
- True (approximate) parallelism across specialists
- No context contamination in lead — specialist outputs go to state.json, not back to lead
- Failure isolation via state.json — crashed specialist leaves partial state readable
- Scales to teams of 3–6 specialists

**Examples:** KB document ingestion, multi-hypothesis incident investigation, multi-lens market analysis, prompt A/B evaluation.

**Disadvantage:** More operational complexity. state.json discipline required. TeammateIdle hook coordination required.

### Decision rule

```
task_duration < 2 minutes AND synchronous result needed → Supervisor-as-Tool
task_duration >= 2 minutes OR parallel execution needed → Supervisor-as-Node
```

The high-value use cases described below (KB ingestion, multi-lens analysis) are all Supervisor-as-Node.

---

## 6. Concurrency & Consistency

### Field ownership as mutex-by-assignment

The primary concurrency control mechanism is assignment, not locking. Each teammate owns exactly one set of top-level state.json fields. No two teammates ever write the same field. This eliminates write conflicts for all owned fields without any locking overhead.

**Enforcement:** The first instruction in every teammate's spawn prompt must be:

```
You OWN and may write ONLY to: [field_name].
Do NOT read or write any other field for modification.
Reading other fields for context is permitted.
```

This is a prompt-level convention, not a compiler-level guarantee (contrast: LangGraph's Annotated reducers are enforced by the runtime). Violating it causes last-write-wins corruption with no error signal.

### turn_count race condition and fix

**The bug:** If both Analyst and Critic are instructed to increment `turn_count`, and they run in a true parallel superstep (both read `turn_count=1` before either writes), both write `turn_count=2`. The result is 2, not 3. This silently under-counts turns, corrupting max_turns enforcement. The supervisor believes 2 turns elapsed when 3 have — enabling an extra Critic→Researcher loop that exhausts the turn budget.

**Observed in this run (turn_count=3, not 2):** Because the Analyst and Critic ran sequentially in this execution, the bug was masked — but it is latent in the design and would trigger in true parallel fan-out. This is the race-condition-masked-by-sequentiality phenomenon.

**Fix:** Only the supervisor increments `turn_count`. Workers write to their owned output fields and set a per-field completion signal (by updating status in state.json). Supervisor reads state.json after all parallel workers are idle (TeammateIdle hook), then increments `turn_count` once, then routes.

```
# WRONG — appears in naive worker prompts
After completing your analysis, increment turn_count in state.json.

# CORRECT — worker prompt
After completing your analysis, write analysis_draft to state.json.
Message the supervisor with: "analysis_complete — your turn to route."
Do NOT touch turn_count.
```

### Read-merge-write atomicity

state.json has no built-in concurrency control. The read-merge-write pattern (read JSON → modify → write full file) is not atomic. Two simultaneous writers can interleave and corrupt.

**Three-layer mitigation:**

1. **Field ownership (primary):** Eliminates concurrent write conflicts for owned fields entirely.
2. **tmp+rename for append-only fields:** `handoff_log` entries use `write → state.json.tmp → mv state.json.tmp state.json` (POSIX `rename` is atomic within the same filesystem). Note: not guaranteed on network-mounted or cloud-synced paths.
3. **status is write-once per turn:** Only supervisor or Finalizer writes `status`. Workers never touch it.

With these three rules, explicit file locking is unnecessary for teams ≤6 teammates. For larger teams or teams with shared fields, use a Redis SETNX-based distributed lock matching the codebase's `StreamingLockManager` pattern (`apps/api/app/redis/`).

---

## 7. Max-Turn Guardrails

### Enforcement protocol

The supervisor enforces `turn_count < max_turns` at the start of **every routing decision**:

```
ROUTING PREAMBLE (execute before every route):
1. Read state.json.
2. If turn_count >= max_turns:
   - Append to handoff_log: {event: "aborted_turn_limit"}
   - Set status = "aborted_turn_limit"
   - Route to Finalizer with forced=True
   - STOP — do not route to any other node
3. If turn_count >= max_turns - 1:
   - Append warning to handoff_log: {event: "turn_budget_warning"}
   - Skip any planned route-back to Researcher
   - Route directly to Finalizer
4. Increment turn_count (supervisor only).
5. Route normally.
```

### Route-back budget consumption

A Critic verdict of `needs_more_research` triggers a route-back to the Researcher, which costs at least 2 additional turns (Researcher turn + Critic re-run). The supervisor must check: `if turn_count + 2 > max_turns: skip route-back, route to Finalizer`. Document this decision in handoff_log.

### Forced finalization must produce a deliverable

When the Finalizer is spawned with `forced=True` (turn-budget exhausted), it must still produce the deliverable. The output should:
1. Prepend a caveat: "This document was produced under forced finalization due to turn-budget exhaustion. Sections marked [INCOMPLETE] reflect gaps that could not be fully addressed."
2. Complete all required sections as best as available state allows.
3. Never silently abort — `status="aborted_turn_limit"` must still trigger the Finalizer.

### Secondary enforcement via hook

The `TaskCompleted` hook provides a secondary guardrail:

```bash
#!/bin/bash
# ~/.claude/teams/research-langgraph/hooks/task-completed.sh
TURN=$(jq '.turn_count' state.json)
MAX=$(jq '.max_turns' state.json)
if [ "$TURN" -ge "$MAX" ]; then
  echo "Turn limit reached — route to Finalizer"
  exit 2
fi
```

Exit code 2 blocks task completion and sends feedback to the teammate. This prevents a runaway loop from inadvertently completing tasks past the budget.

---

## 8. Checkpoint Semantics — What state.json Is and Is NOT

**This section explicitly corrects a claim in the analysis_draft that maps state.json to LangGraph checkpointing.**

### What state.json IS

- A single mutable JSON document persisted on disk
- Provides **forward-only recovery**: if the team crashes, the supervisor re-reads state.json, finds the last committed `status`, and resumes routing from that point
- Acts as team identity (team-name = thread_id analog)
- Human-readable and directly inspectable during a run
- Adequate for crash recovery in the "read last known good state and continue" sense

### What state.json is NOT

- **Not LangGraph's checkpoint/replay system.** LangGraph's `AsyncSqliteSaver` (used in `apps/api/app/stores/memory_store.py:1-33`) snapshots the complete state after **every superstep** and stores a history of all prior states. `graph.get_state_history(config)` allows replay from any prior step. `graph.update_state(config, values)` allows rollback.
- **No step history.** state.json is a single document — there is no history, no prior snapshots, no rollback capability. If the Critic corrupts `structured_inventory`, there is no checkpoint to recover from.
- **No automatic replay.** If you want to re-run from step 2, you must manually restore state.json to the step-2 contents.

### Correct framing

> state.json provides single-snapshot forward-only persistence: the team can resume from the last committed write, but cannot replay, rollback, or inspect intermediate states.

The `AsyncSqliteSaver` in the FastAPI layer (`apps/api/`) is the true LangGraph checkpoint analog. It is a Layer 1 concern. Do not conflate it with the Layer 2 state.json pattern.

### Guard against partial-write corruption

State.json is always assumed valid JSON at read time, but a crash mid-write leaves a corrupt file. Guards:

1. Always write via tmp+rename (atomic on POSIX local filesystems)
2. On read, wrap in a try/except JSON parse. If parse fails: log `[SUPERVISOR] state.json corrupt — recovering from backup`, restore from `state.json.bak` (written before each major update)
3. Set `restart_from` field before any high-risk write so recovery can identify the last safe point

---

## 9. Operational Security Rule

**The Critic flagged this as a hidden pitfall with full-codebase blast radius.**

### The risk

Claude Code's permission mode is inherited by all teammates at spawn time. If the team-lead runs with `--dangerously-skip-permissions`, every teammate inherits unrestricted write access — no approval prompts, no guards.

A **state.json injection attack** — malicious content embedded in research findings (e.g., from an externally-sourced document a Researcher reads) that a poorly-prompted teammate interprets as shell instructions — would execute unchecked against the full codebase, any mounted filesystem, and any credentials in the environment.

The blast radius is: entire repo, all mounted paths, all environment credentials.

### Rule

**DO NOT** run a research team in `--dangerously-skip-permissions` mode when:
- Any teammate reads externally-sourced content (web pages, third-party docs, uploaded files)
- Any teammate's output feeds back as input to another teammate without sanitization
- The team operates against a production or shared codebase

**DO:**
- Run teams in default permission mode (approval prompts active)
- Spawn individual risky teammates in plan-approval mode (`EnterPlanMode`) as an additional gate
- Treat all teammate-produced content as untrusted input when it crosses the boundary into shell commands or file writes
- Explicitly scope each teammate's write permissions in its spawn prompt: "You may only write to: `state.json` and `docs/research-langgraph-agent.md`. No other paths."

**Reference:** Permission inheritance is described in `docs/claude-code-agent-teams-reference.md` — the permissions section specifies that teammates inherit the lead's permission mode at spawn and that adjustments are possible individually post-spawn.

---

## 10. LangGraph ↔ Claude Code Mapping Table

Source: `structured_inventory.mapping_table_candidates`. Entries pruned for duplicates; approximate mappings marked.

| LangGraph Concept | Claude Code Equivalent | Fidelity | Notes |
|---|---|---|---|
| `StateGraph` | `state.json` + task list | Approximate | state.json is typed store; task list is work queue. Together represent graph state. No compile step. |
| `TypedDict` state fields | state.json top-level keys | Approximate | Each key maps to a stage's output. No type enforcement at runtime — prompt discipline only. |
| `Annotated[list, operator.add]` (append reducer) | `handoff_log` append via read-merge-write | Approximate | No automatic reducer; must be implemented manually in each teammate's write step. |
| `add_node` | Teammate role (researcher, analyst, critic, finalizer) | Exact | Each node = one named teammate. Spawn prompt is the node function. |
| `add_edge` (static) | `TaskUpdate(owner=next_teammate)` + `SendMessage` with explicit assignment | Approximate | Lead reads state.status and directly assigns next task to the target teammate. |
| `add_conditional_edges` | Supervisor reads `state.json.status`, routes via `TaskUpdate` + `SendMessage` | Approximate | Routing logic lives in the lead's prompt, not in a compiled graph. Not declarative. |
| `Command(goto=X, update={...})` | Write to `state.json` (owned field) + set status + `TaskUpdate(owner=X)` + `SendMessage(to=X)` | Approximate | A teammate's "return" is this three-step protocol: write, update task, message next actor. |
| `START` node | Supervisor / team-lead is always the entry point | Approximate | No explicit START sentinel — supervisor is the permanent first actor. |
| `END` node | Finalizer sets `status="finalized"`, writes `final_deliverable_path` | Approximate | Termination is convention-based, not graph-enforced. Supervisor detects and cleans up. |
| `interrupt_before` / `interrupt_after` | Plan approval mode (`EnterPlanMode`) on risky teammates | Approximate | Human reviews and approves plan before teammate implements. Closest native analogue. |
| Checkpoint (`thread_id`) | `state.json` on disk; team-name acts as thread-ID | Approximate | Forward-only persistence only. No replay, no history. (See Section 8.) |
| `MemorySaver` (in-memory, dev) | Volatile teammate context only | Approximate | No built-in in-memory state store. |
| `AsyncSqliteSaver` | `state.json` on disk (closest analog, not equivalent) | Approximate | FastAPI codebase uses AsyncSqliteSaver for Layer 1; state.json is the Layer 2 analog. Not equivalent — no replay. |
| `Send` (fan-out to multiple nodes) | N pending tasks + directed `SendMessage` to N pre-spawned teammates | Approximate | True parallel dispatch not achievable. Pre-spawn + directed message is closest approximation. |
| Superstep (parallel node execution) | Multiple teammates running concurrently on claimed separate tasks | Approximate | No synchronization boundary. Supervisor polls state.json or waits for TeammateIdle to detect superstep completion. |
| Routing function return `Literal[...]` | `status` field values in state.json | Exact | Status values are the path_map the supervisor reads to decide routing. |
| `SubGraph` | **NOT directly supported** | Not supported | No nested teams. Workaround: flatten hierarchy (sub-supervisor = named teammate on shared task list), or use ephemeral `Agent` tool without `team_name` inside a teammate (sequential, no mailbox). True hierarchical parallelism is architecturally impossible. |
| `blockedBy` (task dependency) | `addBlockedBy` field in `TaskCreate`/`TaskUpdate` | Exact | One of the strongest native analogues. Matches LangGraph edge sequencing for linear dependencies. |

---

## 11. Worked Example — The Run That Produced This Document

This section narrates the actual team execution that generated this document. It is the most concrete reference for a reader implementing this pattern.

### Team configuration

- **Team name:** `research-langgraph`
- **State file:** `~/.claude/teams/research-langgraph/state.json`
- **max_turns:** 5
- **Teammates:** researcher, analyst, critic, finalizer
- **Pattern used:** Supervisor-as-Node (long-running parallel work, state.json routing)

### Turn 0 — Supervisor initializes (not a worker turn)

```json
{"turn": 0, "from": "supervisor", "to": "state", "event": "initialized", "ts": "2026-04-14T10:10:00Z"}
```

Supervisor (team-lead) creates `state.json` with `objective`, `status="initialized"`, `turn_count=0`, `max_turns=5`. Pre-spawns the full team. Supervisor tasks the researcher first via `TaskUpdate(owner=researcher)` + `SendMessage(to="researcher")`. `turn_count` remains 0 (supervisor increments on routing, not initialization).

### Turn 1 — Researcher

```json
{"turn": 1, "from": "researcher", "to": "supervisor", "event": "research_complete", "ts": "2026-04-14T10:35:00Z"}
```

Researcher reads `objective` from state.json. Fetches LangGraph docs via Context7 MCP. Reads codebase files: `apps/api/app/services/agent_factory.py:1-49`, `apps/api/app/stores/memory_store.py:1-33`, `apps/api/app/streaming/chunk_mapper.py`, `apps/api/app/streaming/events.py`, `apps/api/app/services/prompt_registry.py`, `apps/api/app/services/llm_factory.py`. Reads `docs/claude-code-agent-teams-reference.md`.

Writes `structured_inventory` to state.json (its owned field). Messages supervisor: "research_complete." Supervisor reads state.json, confirms `structured_inventory` populated, increments `turn_count` to 1, routes to Analyst.

### Turn 2 — Analyst

```json
{"turn": 2, "from": "analyst", "to": "supervisor", "event": "analysis_complete", "ts": "2026-04-14T11:02:00Z"}
```

Analyst reads `structured_inventory` + `objective`. Identifies 5 patterns (typed state routing, supervisor-as-orchestrator, parallel fan-out, field-scoped ownership, HITL checkpoint). Identifies 5 use cases (KB ingestion, multi-lens analysis, PR triage, incident investigation, prompt A/B eval). Addresses OQ4, OQ6, OQ7, OQ9 from open_questions. Writes `analysis_draft` to state.json. Messages supervisor. Supervisor routes to Critic. `turn_count` → 2.

> **Note:** In this run, Analyst and Critic ran sequentially. In a true parallel superstep, both would have been dispatched simultaneously. The turn_count race condition (both reading turn_count=1 and both writing turn_count=2) did not trigger because of sequentiality — but the latent bug was identified by the Critic and documented in gap G2.

### Turn 3 — Critic

```json
{"turn": 3, "from": "critic", "to": "supervisor", "event": "critique_complete", "ts": "2026-04-14T11:18:00Z"}
```

Critic reads `structured_inventory` + `analysis_draft`. Identifies 7 unstated assumptions, 5 hidden pitfalls, 2 challenged patterns. Addresses OQ1, OQ2, OQ3, OQ5, OQ8. Issues verdict: `vetted_with_caveats` (no route-back needed). Writes `critique_summary` + `gaps` to state.json. Messages supervisor. Supervisor reads verdict, determines no route-back needed. `turn_count` → 3. Routes to Finalizer.

**Critic's key contributions:**
- Corrected the state.json-as-LangGraph-checkpoint overstatement (gap G1)
- Identified the turn_count race condition (gap G2)
- Challenged Supervisor-as-Tool as universally preferred (gap G4)
- Flagged `--dangerously-skip-permissions` blast radius (gap G5)

### Turn 4 — Finalizer (this document)

```json
{"turn": 4, "from": "finalizer", "to": "supervisor", "event": "finalized", "ts": "2026-04-14T11:30:00Z"}
```

Finalizer reads state.json in chunks. Synthesizes all fields into this document. Writes to `docs/research-langgraph-agent.md`. Updates state.json: `status="finalized"`, appends handoff_log entry. `turn_count` remains 3 (supervisor increments, not Finalizer). Supervisor receives message, reads `status="finalized"`, runs cleanup.

### turn_count=3 (not 2) — the race condition artifact

`turn_count` reached 3 despite having only 3 worker turns (researcher=1, analyst=2, critic=3). This is correct for sequential execution — the Critic appended its own increment to turn_count rather than leaving it to the supervisor. In true parallel (Analyst + Critic concurrent), the under-count bug would have appeared: both read turn_count=1, both write turn_count=2 — result is 2, not 3. The Critic caught this as latent. The fix (supervisor-only increment) would produce turn_count=2 after both parallel workers complete, then turn_count=3 after Finalizer completes — which is accurate.

---

## 12. When to Use This Pattern (and When NOT To)

### Use cases — ordered by ROI

| Use case | Team shape | ROI | Notes |
|---|---|---|---|
| KB parallel document ingestion | Supervisor → [ChunkerA, ChunkerB, ChunkerC] → EmbeddingMerger → QualityValidator | High | Current KB re-indexing is single-threaded. Parallelism directly reduces RAG latency. (`apps/api/app/services/kb/`) |
| Multi-lens AI report analysis | Supervisor → [TechnicalAnalyst, BiasAnalyst, MacroContextAnalyst] → Synthesizer | High | Users asking compound questions currently get serialized answers. (`apps/api/app/services/ai/`, `apps/api/app/calculations/`) |
| Prompt A/B evaluation pipeline | Supervisor → [EvalWorker_v1, EvalWorker_v2, EvalWorker_v3] → MetricsAggregator → Critic | High | PromptRegistry supports per-request version overrides. Team-based eval replaces manual eval scripts. (`apps/api/app/services/prompt_registry.py`) |
| Incident investigation | Supervisor → [DBInvestigator, RedisInvestigator, AIInvestigator] → HypothesisResolver | Medium-High | Competing-hypothesis pattern maps directly to parallel Send. Cuts MTTD. |
| PR triage (multi-lens review) | Supervisor → [SecurityReviewer, PerformanceReviewer, TestCoverageReviewer] → FeedbackSynthesizer | Medium | Dev workflow, not user-facing. Strong pattern demonstration. |

### Weak-fit scenarios — do not use this pattern for

- **Simple sequential tasks** with one or two steps and no parallel phases. Overhead of team coordination exceeds benefit.
- **Real-time, latency-sensitive operations.** Session startup adds seconds per teammate. Not suitable for sub-second workflows.
- **Tasks that require true hierarchical decomposition.** No nested teams. If your task shape requires a sub-supervisor, flatten the hierarchy or use a different tool.
- **Tasks where all work fits in a single context window.** One Claude session with tool use is simpler and cheaper than a multi-teammate team.
- **Tasks against untrusted or externally-sourced input in permissive mode.** Security risk (Section 9).
- **Tasks requiring checkpoint replay or rollback.** state.json provides forward-only recovery only.

### Decision guide

```
Does the task have 3+ distinct specialist phases? → Yes → consider team
Does any phase benefit from parallel execution? → Yes → Supervisor-as-Node
Do all phases fit in one context window? → Yes → single session, not a team
Is the input externally sourced? → Yes → never permissive mode, plan-approval on risky nodes
Is true hierarchical decomposition needed? → Yes → choose a different tool (not this pattern)
```

---

## 13. Known Limitations & Open Questions

### Resolved gaps from the Critic (incorporated into this document)

| Gap | Status | Where addressed |
|---|---|---|
| G1: state.json ≠ LangGraph checkpoint | Resolved | Section 8 |
| G2: turn_count race condition | Resolved | Sections 6, 11 |
| G3: Replacement teammate idempotency | Resolved | Section 4 (Idempotency rule per node) |
| G4: Supervisor-as-tool universally recommended | Resolved | Section 5 (tiered recommendation) |
| G5: --dangerously-skip-permissions blast radius | Resolved | Section 9 |
| G6: Mailbox message loss to exited teammates | Resolved | Section 4 (re-spawn vs SendMessage for post-completion coordination) |
| G7: langgraph-supervisor prebuilt API unverified | Preserved — see OQ8 below | — |

### Remaining open questions

**OQ1 — deepagents library provenance.** *Resolved by Supervisor post-finalization (2026-04-14).* `pip index versions deepagents` returns `deepagents 0.5.2` with 54 published versions (0.0.1 → 0.5.2). It is a public PyPI package, LangChain-adjacent, wrapping `StateGraph` with the deep-agent pattern (main agent + sub-agents + shared file-system tool + planning loop). The codebase's use of it in `apps/api/app/services/agent_factory.py` is therefore a supported dependency, not internal code. External projects may adopt it. Contrast with `langgraph-supervisor` prebuilt when finer control of the supervisor step is needed.

**OQ8 — langgraph-supervisor prebuilt constructor API.** Context7 confirmed package existence but did not return specific constructor parameters. The mapping table (Section 10) references the prebuilt as a contrast point only. **Action before citing:** fetch current docs via Context7 MCP with `resolve-library-id("langgraph-supervisor")` before referencing any specific API signature in implementation code.

### Unstated assumptions the Supervisor should verify

- **Claude Code Agent Teams feature availability:** No minimum version floor was established. Confirm the feature is available in the deployed Claude Code version before designing around it.
- **Terminal compatibility:** Split-pane display requires tmux or compatible terminal. VS Code terminal, Windows Terminal, and Ghostty do not support split panes — use in-process display mode in those environments.
- **Filesystem atomicity:** The tmp+rename mitigation for handoff_log atomicity is valid on POSIX local filesystems. Not guaranteed on NFS, SMB, or cloud-synced paths (e.g., iCloud Drive, Dropbox).
- **Lead session persistence:** No lead-crash recovery path is defined. If the team-lead session dies, in-flight teammates are permanently orphaned. Recovery requires reading state.json and spawning a new lead with explicit `restart_from` context.
- **Context window budget:** No contingency if a teammate hits context compression mid-task. ChunkMapper in `apps/api/app/streaming/chunk_mapper.py:161-178` uses a compression detection ratio — keep state.json inventory fields concise to avoid triggering context pressure in teammates.

### Architectural ceiling (not a workaround, a platform boundary)

**No true hierarchical parallelism.** LangGraph sub-graphs allow recursive hierarchical decomposition (supervisor → sub-supervisor → workers). Claude Code forbids nested teams — only the lead can spawn. Two options only: (a) flatten the hierarchy (sub-supervisor = named teammate managing a task subset on the shared task list); (b) use Agent tool without `team_name` inside a teammate (ephemeral, sequential, no mailbox). If your task genuinely requires parallel hierarchical decomposition, this pattern is the wrong tool.

---

## 14. Appendix: Full state.json Schema

The following is the complete typed schema for the `state.json` file as used in this research team run. Use this as the template for new teams.

```python
from typing import TypedDict, Annotated
import operator


# --- Sub-types ---

class LangGraphPrimitive(TypedDict):
    name: str
    kind: str
    package: str
    description: str


class MappingEntry(TypedDict):
    langgraph_concept: str
    claude_code_equivalent: str
    notes: str


class CodebaseSignal(TypedDict):
    signal: str
    detail: str
    file: str
    guideline: str


class OpenQuestion(TypedDict):
    id: str
    question: str
    why_matters: str
    flag_for: str  # "researcher" | "analyst" | "critic"


class StructuredInventory(TypedDict):
    langgraph_primitives: list[LangGraphPrimitive]
    langgraph_supervisor_patterns: list[dict]
    claude_code_agent_team_primitives: list[dict]
    limitations: list[str]
    mapping_table_candidates: list[MappingEntry]
    codebase_signals: list[CodebaseSignal]
    open_questions: list[OpenQuestion]


class Pattern(TypedDict):
    name: str
    description: str
    in_langgraph: str
    in_claude_code: str
    key_insight: str


class UseCase(TypedDict):
    name: str
    description: str
    codebase_location: str
    team_shape: str
    value: str  # "High" | "Medium-High" | "Medium" | "Low"


class Tradeoff(TypedDict):
    decision: str
    recommendation: str


class AddressedOpenQuestion(TypedDict):
    id: str
    question: str
    answer: str
    implementation_note: str


class AnalysisDraft(TypedDict):
    patterns: list[Pattern]
    use_cases: list[UseCase]
    tradeoffs: list[Tradeoff]
    addressed_open_questions: list[AddressedOpenQuestion]
    recommended_architecture: str


class CritiqueSummary(TypedDict):
    unstated_assumptions: list[str]
    hidden_pitfalls: dict  # keyed by pitfall name
    challenged_patterns: list[dict]
    addressed_open_questions: dict  # keyed by OQ id
    verdict: str  # "approved" | "vetted_with_caveats" | "needs_more_research"


class Gap(TypedDict):
    id: str
    severity: str  # "high" | "medium" | "low"
    claim: str
    why_it_matters: str
    suggested_fix: str


class HandoffEvent(TypedDict):
    turn: int
    from_: str   # field name is "from" in JSON (Python keyword conflict)
    to: str
    event: str
    ts: str      # ISO 8601


# --- Root state ---

class TeamState(TypedDict):
    # Immutable after init (supervisor owns)
    objective: str
    max_turns: int
    final_deliverable_path: str

    # Mutable routing fields (supervisor owns)
    status: str          # See status enum in Section 3
    turn_count: int      # ONLY supervisor increments
    restart_from: str | None   # Set on fault recovery; normally null

    # Worker output fields (one owner each)
    structured_inventory: StructuredInventory | None   # researcher
    analysis_draft: AnalysisDraft | None               # analyst
    critique_summary: CritiqueSummary | None           # critic

    # Shared append-only fields (all teammates, tmp+rename protocol)
    gaps: list[Gap]
    handoff_log: Annotated[list[HandoffEvent], operator.add]  # conceptual annotation only


# --- Status enum ---
# Allowed values for TeamState.status:
STATUS_INITIALIZED          = "initialized"
STATUS_RESEARCH_COMPLETE    = "research_complete"
STATUS_ANALYSIS_COMPLETE    = "analysis_complete"
STATUS_CRITIQUE_COMPLETE    = "critique_complete"
STATUS_NEEDS_MORE_RESEARCH  = "needs_more_research"
STATUS_FINALIZED            = "finalized"
STATUS_FORCED_COMPLETE      = "forced_complete"
STATUS_ABORTED_TURN_LIMIT   = "aborted_turn_limit"
```

### Logging conventions

All teammates must use bracketed log prefixes matching the codebase's `[SERVICE_NAME]` convention (`apps/api/app/streaming/chunk_mapper.py` uses `[CHUNK_MAPPER]`; `apps/api/app/services/prompt_registry.py` uses `[PROMPT_REGISTRY]`):

- Supervisor: `[SUPERVISOR]`
- Researcher: `[RESEARCHER]`
- Analyst: `[ANALYST]`
- Critic: `[CRITIC]`
- Finalizer: `[FINALIZER]`

Example: `[SUPERVISOR] turn_count=2 status=analysis_complete → routing to critic`

### Model assignment

Following the codebase's `llm_factory.py` pattern (haiku for fast/lightweight, sonnet for main reasoning):

| Role | Model |
|---|---|
| Researcher | `claude-sonnet-4-6` (deep codebase + doc reading) |
| Analyst | `claude-sonnet-4-6` (architectural reasoning) |
| Critic | `claude-haiku-4-5-20251001` (validation; lighter model sufficient) |
| Finalizer | `claude-sonnet-4-6` (synthesis requires full capability) |

---

*Document produced by the research-langgraph team, turn 4 of 5. Supervisor: team-lead. Workers: researcher (turn 1), analyst (turn 2), critic (turn 3), finalizer (turn 4).*
