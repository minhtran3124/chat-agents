# Deep Agents Harness — Upgrade Milestones

> **Companion to**: `deep-agents-harness-upgrade-roadmap.md` (analysis + decisions). This doc is the **execution-tracking** artifact — what "done" looks like per phase, in what order, with what tests.
> **Stance locked**: Hybrid (own product surfaces, outsource runtime + tracing + sandbox)
> **Date started**: 2026-04-24
> **Status**: All phases are **planned**, none in flight yet.

---

## 1. Decisions Locked In (this conversation)

| # | Decision | Implication |
| :-- | :--- | :--- |
| 1 | **Hybrid ownership stance** | Own prompts / tools / SSE contract / guardrails / supervisor. Outsource `deepagents` runtime, LangSmith tracing, sandbox vendor, MCP servers. **Drop Langfuse** (LangSmith covers tracing). **Defer Prometheus, mem0+pgvector, Postgres migration** until usage data justifies. |
| 2 | **Phase 2 is split into two PRs** | PR 2a = guardrails (input + output factory nodes). PR 2b = HITL (gated tool + `interrupt()` + resume endpoint + frontend approval UI). Review each in isolation. |
| 3 | **Sandbox via abstract interface** | Use E2B as first implementation, but code against a `SandboxExecutor` protocol so swapping to Modal, Daytona, or self-hosted Docker/Firecracker later is a one-class change. See §4 for the shape. |
| 4 | **Eval baseline = 20 questions** | Enough for smoke-test signal, cheap to run nightly, room to grow. Baseline scores snapshotted at Phase 5 land. |
| 5 | **Out of scope (for now)** | Caching layer · multi-model routing · voice · image · any new modality. Captured in §10 parking lot. Future PR per item, not bundled into this roadmap. |

---

## 2. Ownership Matrix (hybrid resolved)

| Concern | Owner | Notes |
| :--- | :--- | :--- |
| Graph runtime | **Outsource** | `deepagents` 0.5+ — upgraded in Phase 0 |
| Tracing | **Outsource** | LangSmith only; Langfuse dropped |
| LLM metrics | **Outsource** | LangSmith analytics cover tokens/latency/cost |
| HTTP metrics | **Defer** | Prometheus only if Phase 6 picks self-owned infra |
| Checkpoint store | **Own (SQLite)** | Migrate to Postgres or Deep Agents Deploy at Phase 6 decision |
| Semantic memory | **Defer** | Current `InMemoryStore` fine until product demand; won't add mem0 preemptively |
| Guardrails | **Own** | Factory-node pattern (`apps/api/app/guardrails/`) |
| Supervisor | **Own** | `langgraph-supervisor` wrapping Deep Agent subagents |
| Prompts & versioning | **Own** | Already in place, best-in-class vs. reference |
| SSE contract | **Own** | Already in place, extend per phase |
| HITL primitive | **Own (via LangGraph)** | `interrupt()` + resume endpoint |
| Code sandbox | **Outsource w/ swap seam** | `SandboxExecutor` protocol, E2B default |
| MCP tool servers | **Outsource** | Run as separate processes; client via `langchain-mcp-adapters` |
| Eval rubrics & CI gate | **Own** | Auto-discovered markdown metrics, LangSmith annotations |
| Auth / rate limiting | **Defer** | Only when multi-tenant need appears (Phase 6) |
| Durable execution | **Defer** | Only when long runs matter (Phase 6) |

---

## 3. Dependency graph

```
Phase 0 (fixes)
   │
   ▼
Phase 1 (obs + budget)  ─────────────▶  Phase 5 (eval)
   │
   ▼
Phase 2a (guards)
   │
   ▼
Phase 2b (HITL)  ──┬──▶ Phase 3a (supervisor)
                   │         │
                   │         ▼
                   │    Phase 3b (MCP)
                   │
                   └──▶ Phase 4 (sandbox) ──┐
                                            ▼
                                      Phase 6 (deploy decision)
```

Critical path: Phase 0 → 1 → 2a → 2b → 4 (HITL-gated sandbox is the highest-novelty capability). Phase 3 (supervisor + MCP) and Phase 5 (eval) can run in parallel once Phase 1 lands if you have capacity.

---

## 4. Sandbox abstraction (Phase 4 design lock)

To honor decision #3 ("use vendor but keep ability to self-own later"), Phase 4 ships an abstract `SandboxExecutor` — not a direct E2B call.

```python
# apps/api/app/tools/sandbox/base.py
from typing import Protocol
from pydantic import BaseModel

class SandboxResult(BaseModel):
    stdout: str
    stderr: str
    error: str | None
    exit_code: int
    duration_ms: int

class SandboxExecutor(Protocol):
    async def run_code(self, code: str, timeout_s: int = 30) -> SandboxResult: ...

# apps/api/app/tools/sandbox/e2b_executor.py   (default)
class E2BExecutor:
    async def run_code(self, code, timeout_s=30) -> SandboxResult:
        async with Sandbox(template="base", timeout=timeout_s) as sbx:
            r = await sbx.run_code(code)
            return SandboxResult(stdout=r.text, stderr="", error=None,
                                  exit_code=0, duration_ms=r.duration_ms)

# apps/api/app/tools/sandbox/local_docker.py   (future, when self-owning)
class LocalDockerExecutor:
    async def run_code(self, code, timeout_s=30) -> SandboxResult:
        # spawn a Firecracker/gVisor/Docker container with resource limits
        ...

# apps/api/app/tools/sandbox/factory.py
def get_sandbox_executor(settings) -> SandboxExecutor:
    backend = settings.SANDBOX_BACKEND  # "e2b" | "local_docker" | ...
    return {"e2b": E2BExecutor, "local_docker": LocalDockerExecutor}[backend]()
```

The `python_exec` tool resolves the executor from settings at build time and is backend-agnostic. Migration later = new executor class + config flip, no tool-level changes.

---

## 5. Milestone cards

Each card is self-contained. `Effort` is focused work days; calendar time assumes 60% focus.

### Phase 0 — Stabilize foundation · 0.5 day

- **Goal**: Close latent bugs so the SSE contract is consistent before adding features.
- **Acceptance**:
  - [ ] `stream_end` fires on every terminal path, including exceptions.
  - [ ] `memory_updated` decision made: emitted from store-write listener **or** removed from `SSEEventMap` + reducer.
  - [ ] `settings.RESEARCH_TIMEOUT_S` enforced via `asyncio.timeout()` around `astream`.
  - [ ] `deepagents >= 0.5` pinned in `pyproject.toml`; CI green after bump.
- **Deliverables**: 1 PR — `fix(api): stabilize SSE contract + timeout + deepagents 0.5`.
- **Tests**:
  - unit — `research_router` emits `stream_end` when the generator raises.
  - e2e — simulated slow tool triggers `asyncio.TimeoutError` → `error` + `stream_end`.
- **Success metric**: UI is never stuck in `"streaming"` state under any server-side failure.
- **Depends on**: — .
- **Out of scope**: Logging, tracing, auth.
- **Risks**: `deepagents` 0.5 behavior changes (subagent async, sandbox defaults) may ripple into `chunk_mapper`. Mitigate by running the existing 27 chunk-mapper tests first and only then cutting the PR.

### Phase 1 — Observability & budget · 1–2 days

- **Goal**: See every run in LangSmith; cap what any single run can cost.
- **Acceptance**:
  - [ ] LangSmith shows a trace for every `/research` call, including supervisor+subagent hierarchy.
  - [ ] All application logs are structured JSON with `thread_id`, `request_id`, `prompt_versions` bound from context.
  - [ ] Token-budget guard aborts runs over `MAX_TOKENS_PER_RUN` (env var; default 200k).
  - [ ] New SSE event `budget_exceeded` fires; frontend surfaces it distinctly from `error`.
- **Deliverables**: 1 PR — `feat(api,web): langsmith tracing + structlog + token budget`.
  - `apps/api/app/observability/structlog_setup.py` + context middleware.
  - Token counter wrapping `astream` in `routers/research.py`.
  - `events.py` factory + `SSEEventMap` + `useResearchStream` reducer case.
  - `.env.example` with `LANGCHAIN_TRACING_V2`, `LANGCHAIN_PROJECT`, `LANGCHAIN_API_KEY`, `MAX_TOKENS_PER_RUN`.
  - `CONTRIBUTING.md` section: "Enabling tracing locally".
- **Tests**:
  - unit — token counter sums usage chunks correctly; `budget_exceeded` payload shape.
  - unit — structlog context binds thread_id and survives across `await`.
  - e2e — over-budget request yields `budget_exceeded` + `stream_end`.
- **Success metric**: One reviewer can open a LangSmith trace for a prod run and debug without asking questions; synthetic over-budget test fails fast.
- **Depends on**: Phase 0.
- **Out of scope**: Langfuse, Prometheus, auth, rate limiting.

### Phase 2a — Guardrails (factory pattern) · 1–2 days

- **Goal**: Input and output safety checks as LangGraph-compatible factory nodes, fail-open.
- **Acceptance**:
  - [ ] `input_guardrail` blocks/redacts PII (SSN, credit card via Luhn, API key heuristics) and prompt-injection regex patterns.
  - [ ] `output_guardrail` runs LLM-as-judge via `get_fast_llm()`, annotates unsafe outputs; fail-open on judge errors.
  - [ ] Parent `StateGraph` wraps Deep Agents graph: input_guard → deep_agent → output_guard.
  - [ ] Guard violations logged at WARN with structured context; not a user-visible error by default.
- **Deliverables**: 1 PR — `feat(api): input + output guardrail factory nodes`.
  - `apps/api/app/guardrails/{input,output}.py` + `__init__.py` exposing factories.
  - Wrapper in `services/agent_factory.py`.
- **Tests**:
  - unit — blocks 5 known prompt-injection patterns; passes 5 benign inputs.
  - unit — PII redaction for SSN + CC + API key.
  - unit — output judge fail-open on exception.
- **Success metric**: Known-bad inputs from a small corpus are blocked; benign control inputs pass unchanged.
- **Depends on**: Phase 1 (tracing to debug guard behavior).
- **Out of scope**: HITL, MCP, supervisor.

### Phase 2b — HITL (interrupt + resume) · 2–3 days

- **Goal**: A human approves/edits/rejects any tool tagged `gated` before it fires.
- **Acceptance**:
  - [ ] Gated-tool registry concept: `auto_tools` (Tavily, think_tool) vs `gated_tools` (new `send_email` stub for demo).
  - [ ] Gated tool calls `interrupt(payload)`; ChunkMapper detects `__interrupt__` and emits `approval_required` SSE event.
  - [ ] Frontend shows approval UI (approve / reject / edit fields); `useResearchStream` transitions to `awaiting_approval` sub-state.
  - [ ] `POST /research/resume { thread_id, decision }` continues the graph with `Command(resume=decision)`.
  - [ ] Edited fields from the UI are honored by the tool.
- **Deliverables**: 1 PR — `feat(api,web): HITL interrupt + resume for gated tools`.
  - `apps/api/app/tools/gated/send_email.py` (demo stub).
  - `approval_required` factory + `SSEEventMap` + reducer.
  - `routers/research.py` resume endpoint; schemas for `ResumeRequest`.
  - Frontend: approval modal component; `resume()` call path in `useResearchStream`.
- **Tests**:
  - unit — chunk_mapper converts `__interrupt__` to `approval_required` payload.
  - integration — invoke → `approval_required` → resume(approve) → tool returns expected string.
  - integration — resume(reject) → tool returns cancelled, graph ends cleanly.
  - frontend — approval modal renders, approve POSTs, state transitions correctly.
- **Success metric**: End-to-end HITL demo recorded: question → gated tool call → approval modal → approve with edit → tool returns edited payload → `stream_end` with correct final report. LangSmith trace shows the pause.
- **Depends on**: Phase 2a (factory pattern groundwork), Phase 1 (trace).
- **Out of scope**: Multi-user approval queues, async approval via webhook, auth.

### Phase 3a — Explicit supervisor · 2–3 days

- **Goal**: Swap Deep Agents' implicit `task` routing for an explicit supervisor we can test.
- **Acceptance**:
  - [ ] `agent_factory.build_research_agent()` returns `create_supervisor([researcher, critic], ...)` compiled graph.
  - [ ] Existing SSE events (`subagent_started`, `subagent_completed`, `text_delta`, `todo_updated`, `file_saved`, `reflection_logged`, `compression_triggered`) all still fire correctly.
  - [ ] At least one unit test asserts supervisor routes to the intended subagent given a deterministic mock.
  - [ ] Prompt registry still feeds supervisor + each subagent their own prompt version.
- **Deliverables**: 1 PR — `refactor(api): explicit supervisor over deep agent subagents`.
  - `langgraph-supervisor` dependency.
  - `services/agent_factory.py` migration.
  - `services/prompt_registry.py` updates if slot names change.
- **Tests**:
  - unit — supervisor's tool calls resolve to correct subagent.
  - e2e — existing SSE e2e tests pass unchanged.
- **Success metric**: No user-visible regression; LangSmith trace now shows supervisor→subagent handoff as a named edge instead of an opaque tool call.
- **Depends on**: Phase 2b (HITL primitive integrated first — don't mix refactor with feature).
- **Out of scope**: MCP, sandbox.

### Phase 3b — MCP client integration · 3–4 days

- **Goal**: Load tools from external MCP servers at runtime; degrade gracefully on failure.
- **Acceptance**:
  - [ ] `settings.MCP_SERVERS` dict: `{ name: { url, transport } }`.
  - [ ] `services/mcp_client.py` uses `MultiServerMCPClient` to load tools at app startup.
  - [ ] MCP tools merged into each subagent's tool list at compile time.
  - [ ] `mcp_status` SSE event fires once at stream start with per-server up/down state.
  - [ ] Server crash or disconnect produces logged warning; agent continues with remaining tools.
- **Deliverables**: 1 PR — `feat(api,web): multi-server MCP tool integration`.
  - `langchain-mcp-adapters` dependency.
  - `services/mcp_client.py` with reconnect-on-`ClosedResourceError`.
  - `mcp_status` event + `SSEEventMap` + frontend chip.
  - `.env.example` documenting `MCP_SERVERS` JSON format.
- **Tests**:
  - unit — degraded-mode returns empty tool list on all-server failure.
  - integration — local stdio MCP fixture server contributes a tool; agent can call it.
  - integration — simulated disconnect mid-run; stream completes with warning log.
- **Success metric**: A question requiring an MCP-provided tool (e.g., a filesystem MCP server `read_file`) completes end-to-end; trace shows the MCP tool call.
- **Depends on**: Phase 3a (supervisor — cleaner tool wiring).
- **Out of scope**: Sandbox, durable execution, per-user MCP auth.

### Phase 4 — Sandboxed code execution · 3–5 days

- **Goal**: A `python_exec` tool that runs model-generated code in an isolated environment, gated by HITL in dev and permission-mode in prod.
- **Acceptance**:
  - [ ] `SandboxExecutor` protocol defined (see §4).
  - [ ] `E2BExecutor` implements it as the default backend; `SANDBOX_BACKEND=e2b` in `.env.example`.
  - [ ] `python_exec` tool resolves executor via factory; timeout enforced.
  - [ ] `settings.SANDBOX_PERMISSION_MODE`: `auto` / `require_approval` / `deny`.
  - [ ] `require_approval` mode integrates Phase 2b `interrupt()` — approval payload includes the code to execute.
  - [ ] Sandbox errors surface as tool results (stderr + exit code); do not crash the stream.
  - [ ] README/CONTRIBUTING documents: "to self-own the sandbox, implement `SandboxExecutor` and set `SANDBOX_BACKEND=<yours>`."
- **Deliverables**: 1 PR — `feat(api): sandboxed python_exec tool (E2B default, pluggable backend)`.
  - `apps/api/app/tools/sandbox/{base,e2b_executor,factory}.py`.
  - `apps/api/app/tools/python_exec.py` using the factory.
  - Tool registered conditionally (settings flag to opt-in).
- **Tests**:
  - unit — factory returns correct executor per setting.
  - unit — `deny` mode returns cancelled without calling executor.
  - integration — `require_approval` → `interrupt` → approve → code runs → result returned.
  - integration — runaway code is killed at timeout; tool returns stderr.
- **Success metric**: "Compute the mean of [1,2,3,4,5]" prompt: agent generates Python, approval prompt appears, approve, sandbox returns `3.0`, LangSmith trace shows the sandbox call.
- **Depends on**: Phase 2b (HITL primitive).
- **Out of scope**: Language sandboxes beyond Python; self-owned backend (parked for Phase 6 / future).
- **Risks**: E2B quota/latency during dev — mitigate with a `local_dev_noop` backend stubbed for tests so we don't burn quota on CI.

### Phase 5 — Eval framework · 4–5 days

- **Goal**: Prevent silent quality regressions when prompts, models, or subagent wiring change.
- **Acceptance**:
  - [ ] `apps/api/evals/metrics/*.md` auto-discovered; each file = one LLM-as-judge rubric.
  - [ ] `apps/api/evals/questions.yaml` with the **20-question baseline** set covering research question shapes seen in prod.
  - [ ] Nightly GitHub Action runs the question set against the current active prompt versions; scores annotate LangSmith runs.
  - [ ] Baseline scores snapshot on first successful run; stored in `apps/api/evals/baselines/YYYY-MM-DD.json`.
  - [ ] CI gate (separate job on PRs) runs the eval on a smaller 5-question subset; fails if any core metric drops > 10% vs. baseline.
- **Deliverables**: 1 PR — `feat(evals): LLM-as-judge harness + baseline + CI gate`.
  - `apps/api/evals/runner.py` + `apps/api/evals/metrics/{relevance,helpfulness,hallucination}.md`.
  - GitHub Action workflow.
  - Baseline snapshot from first nightly run.
- **Tests**:
  - unit — metric file parser handles malformed markdown gracefully.
  - unit — score aggregation produces deterministic output for fixed judge mock.
  - integration — end-to-end eval run against a stubbed agent returns expected shape.
- **Success metric**: Nightly run posts to LangSmith; intentional prompt regression (e.g., replace `main/v3.md` with an empty prompt) triggers CI failure.
- **Depends on**: Phase 1 (LangSmith setup).
- **Out of scope**: Human-labeled golden set; continuous prompt optimization.
- **Risks**: LLM-as-judge variance at 20 questions is real. Mitigate by running each question 3× and taking the mean; accept a wider regression threshold (10% not 5%).

### Phase 6 — Deployment decision point · 1–2 weeks of reflection + chosen path

- **Goal**: Decide self-owned infra vs. Deep Agents Deploy based on ≥ 4 weeks of production data from Phases 0–5.
- **Acceptance**:
  - [ ] Usage report: daily QPS, p50/p95 run duration, error rate, unique thread count, tenant count (if any).
  - [ ] Decision memo comparing Path A (Postgres + Docker Compose + auth + rate limiting + Prometheus) vs. Path B (`deepagents-deploy` migration).
  - [ ] First PR of chosen path merged.
- **Deliverables**:
  - Decision memo at `reseachers/phase-6-deployment-decision.md`.
  - Path A PR or Path B PR as follow-up.
- **Success metric**: CTO signs off on memo; chosen path's first PR open and CI green.
- **Depends on**: Phases 0–5 in production ≥ 4 weeks.
- **Out of scope**: Pre-deciding anything; revisiting the hybrid stance unilaterally.

---

## 6. Timeline (calendar vs. focused)

| Phase | Focused effort | Calendar time (60% focus) | Running total |
| :--- | ---: | ---: | ---: |
| 0 | 0.5 d | 1 d | 1 d |
| 1 | 1.5 d | 2–3 d | 3–4 d |
| 2a | 1.5 d | 2–3 d | 5–7 d |
| 2b | 2.5 d | 4–5 d | 9–12 d |
| 3a | 2.5 d | 4–5 d | 13–17 d |
| 3b | 3.5 d | 5–6 d | 18–23 d |
| 4 | 4 d | 6–7 d | 24–30 d |
| 5 | 4.5 d | 7–8 d | 31–38 d |
| **Subtotal** | **~20 focused days** | **~31–38 calendar days** | |
| Soak period | — | 28 d | ~59–66 d |
| Phase 6 memo + PR | 5 d | 8 d | ~67–74 d |

**Bottom line**: ~3 focused weeks of coding, ~10 calendar weeks to fully-decided state.

---

## 7. Per-phase checklist (copy to PR description)

```markdown
### Phase N Acceptance
- [ ] <copy from milestone card §5>
- [ ] Tests added per card
- [ ] LangSmith trace attached to PR showing the new behavior
- [ ] Doc updated: `reseachers/deep-agents-harness-upgrade-milestones.md` marked phase complete
- [ ] `CHANGELOG.md` entry (if repo adopts one)
```

---

## 8. Rollback strategy

Each phase's PR must be **revertable in one git revert** (no follow-up migrations on the critical path). Concretely:

- Phase 0: revert is safe — only restores previous bug state.
- Phase 1: revert is safe — LangSmith integration is additive; env vars become unused.
- Phase 2a: revert is safe — guardrails are extra nodes; removing them restores current graph.
- Phase 2b: revert is safe **if** no in-flight threads are paused; document in release notes.
- Phase 3a: revert requires care — supervisor swap touches `agent_factory.py`; feature-flag gate via `USE_SUPERVISOR=true` recommended.
- Phase 3b: revert is safe — MCP degrades to "no MCP tools available."
- Phase 4: revert is safe — sandbox tool is opt-in via `SANDBOX_ENABLED=true`.
- Phase 5: revert is safe — eval workflow just stops running.

---

## 9. Open questions parked for resolution during execution

1. **Phase 2b**: Should `approval_required` time out? If the user walks away, does the graph auto-cancel after N minutes, or wait indefinitely via checkpoint?
2. **Phase 3b**: Per-user MCP auth — defer until we have auth at all (Phase 6), or implement token passing in `MCP_SERVERS` config now?
3. **Phase 4**: What's the cost ceiling per `python_exec` call? Need a sub-budget inside the global `MAX_TOKENS_PER_RUN` concept — maybe `MAX_SANDBOX_CALLS_PER_RUN=5`.
4. **Phase 5**: Judge model — same `get_fast_llm()` as guardrails, or a dedicated judge model (often Claude Opus is used to judge Sonnet)? Cost vs. signal quality.

---

## 10. Future extensions (parking lot — **not for now**)

Captured here so they're not forgotten, and so each has a natural Phase-7+ slot when priority appears. **Do not include any of these in Phases 0–6.**

| Extension | Shape when it arrives | Likely dependencies |
| :--- | :--- | :--- |
| **Caching layer** | Semantic cache (embed question → reuse result) OR prompt cache (Anthropic prompt caching, LangSmith cache) | Phase 1 (metrics to prove hit-rate) |
| **Multi-model routing** | Config-driven model selection per subagent/task; fallback chains | Phase 5 (eval per model matters) |
| **Voice input/output** | STT on ingress, TTS on `text_delta` → audio chunks; new SSE event `audio_chunk` | Streaming refactor |
| **Image input** | Multimodal LLM path + image-in-SSE event; Tavily image search mode | Model capability confirmation |
| **Image output** | Tool for generation (DALL-E, Imagen, Stable Diffusion) behind sandbox/permission-mode gate | Phase 4 pattern |
| **Scheduled / cron-style agent runs** | `routines` endpoint; Temporal or cron | Phase 6 (durable execution) |
| **Multi-tenant** | Auth + per-tenant rate limiting + per-tenant MCP config | Phase 6 (self-owned path) |
| **Agent-to-agent protocol** | A2A spec compliance for inter-agent comms | Ecosystem maturity |

Each goes through the same milestone-card format when pulled in; scope creep prevented by keeping them out of the current 0–6 plan.

---

## 11. How to update this doc as work progresses

- Change the `Status` field at the top as phases move.
- Mark acceptance checkboxes as items land.
- When a phase lands, add a "Landed" section under its card with: date, PR link, LangSmith trace link, notes/deviations from the plan.
- If scope shifts mid-phase, edit the card directly — do not let the doc drift from reality. The roadmap doc (`deep-agents-harness-upgrade-roadmap.md`) stays static as the *analysis*; this one is the *living plan*.
