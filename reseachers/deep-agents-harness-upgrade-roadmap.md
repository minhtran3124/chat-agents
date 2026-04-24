# Production-Ready AI Agent Harness — Analysis & Roadmap

> **Produced by**: senior-researcher pass comparing the dev.to "Agent Harness" article against this repo and the wider 2026 agent-framework ecosystem.
> **Primary reference**: [Building a Production-Ready AI Agent Harness — apssouza22, dev.to](https://dev.to/apssouza22/building-a-production-ready-ai-agent-harness-2570)
> **Date**: 2026-04-24
> **Audience**: CTO / senior researcher deciding the next 12-month direction for `chat-agents` (Deep Agents + FastAPI + SSE)
> **Scope**: article breakdown → repo gap analysis → ecosystem survey → phased proposal → code sketches → decision points

---

## 1. Executive Summary

Souza's "Agent Harness" is essentially **"LangGraph with everything around it"** — FastAPI + SSE as the transport, `AsyncPostgresSaver` for checkpointing, mem0 + pgvector for per-user memory, Langfuse + Prometheus + structlog for observability, custom input/output guardrail nodes, and an `MCPSessionManager` for multi-server MCP tools. It is a faithful implementation of the **2026 LangGraph-as-harness consensus** — not a new paradigm, but a well-composed one.

**Your repo is closer to harness-grade than the commit log suggests.** Second-order patterns that the article does not even cover — prompt versioning with per-request overrides (`apps/api/app/services/prompt_registry.py`), a typed SSE contract with 11 event types (`apps/api/app/streaming/events.py`), a chunk mapper with deduplication and 27 unit tests, dual-LLM cost optimization, and `draft.md` fallback recovery — are already in place.

**The gap to close is mostly at the edges**: authz, rate limiting, tracing, token budget, HITL approvals, MCP, and an explicit supervisor. Realistic estimate: **3–4 focused weeks** to reach the equivalent of the dev.to reference, plus genuinely new capability surfaces (HITL, MCP, code-exec) to unlock.

**The biggest strategic question is not "which framework" but "own or outsource the skeleton?"** — do you build a self-owned harness (Souza's path) or gradually move to `deepagents` v0.5 + Deep Agents Deploy / Claude Managed Agents? That decision reshapes Phases 3–4 below.

**Recommended next PR**: Phase 0 (fix latent bugs) + Phase 1 (structured logging + LangSmith tracing + token budget). Value is unambiguous, risk is near zero, and it unblocks every later phase.

---

## 2. What the Article Actually Proposes

### 2.1 Mental model

*Brain vs. skeleton*: agent code is the brain, the harness is the skeleton that carries observability, memory, guardrails, persistence, auth, and deployment. Agents live in self-contained directories under `src/app/agents/`; the harness injects everything else.

### 2.2 Three architecture templates (mixed in one repo)

| Template | When to use | Control | Debuggability | Parallelism |
| :--- | :--- | :--- | :--- | :--- |
| **Custom StateGraph** (guardrail → chat → tool → output) | Deterministic chat / workflow | Full | High | Manual |
| **Multi-agent Subgraphs** (supervisor + researchers via `asyncio.gather`) | Decomposable research tasks | Hierarchical | Medium | Built-in |
| **Deep Agents / ReAct** with skill markdown files | Domain-specific tool-heavy work (SQL, APIs) | Loose | Lower | Sequential |

### 2.3 Production concerns and how each is solved

| Concern | How Souza solves it |
| :--- | :--- |
| **State persistence** | `AsyncPostgresSaver` — checkpoint *every node*, resume by `thread_id` |
| **Per-user long-term memory** | mem0 + pgvector, pulled pre-invocation, written post-invocation in a background `asyncio.create_task` (non-blocking) |
| **Context overflow** | Two-layer: (a) tool results > 80 KB go to disk with head/tail preview in state; (b) at 85% of model window, summarize by splitting at the last `HumanMessage` boundary |
| **Guardrails** | *Factory* nodes returning LangGraph-compatible guards: banned keywords, prompt-injection regex, PII detection (SSN/CC-Luhn/API keys), LLM-as-judge output safety — **fail-open** so the guard itself can't DoS the product |
| **MCP** | `MCPSessionManager` manages multiple SSE MCP servers via `AsyncExitStack`, reconnects on `ClosedResourceError`, merges MCP tools with built-ins at graph compile time |
| **Observability** | Langfuse for traces, Prometheus for metrics (inference duration, tokens by model+agent, tool exec counters), structlog with `LoggingContextMiddleware` that binds session/user IDs from the JWT |
| **Errors/retries** | `model.with_retry(stop_after_attempt=3)` on LLM calls; MCP degrades gracefully to built-in tools |
| **Evals** | LLM-as-judge, auto-discovered markdown metric files, scores pushed back to Langfuse traces |
| **Deployment** | Docker Compose with Postgres+pgvector, Prometheus, Grafana, cAdvisor; non-root container |

### 2.4 What is missing even in the article

Even though it is marketed as production-ready, four load-bearing concerns are absent:

- **No sandbox for code execution.** SQL "safety" is enforced only by prompt text in a skill markdown — hope-based, not isolation-based.
- **HITL is not covered.** No `interrupt()` approve/edit/reject loop shown.
- **No durable-execution layer** (Temporal/Inngest). Postgres checkpointing lets you resume the graph, but in-flight HTTP requests and mid-stream SSE connections are still lost if the FastAPI process dies.
- **No cost caps / token-budget guard** — the retry decorator will cheerfully burn your budget on a model that's hallucinating tool calls.

### 2.5 The most transferable idea

The **factory-function guardrail pattern**: guards are plain LangGraph node factories that return a `Callable`, so you can wire different profiles per agent without duplicating logic. This is strictly better than HTTP middleware for agent systems — middleware can only guard the HTTP edge, while factory guards can sit anywhere in the graph (pre-LLM, post-LLM, pre-tool, per-subagent) and participate in the checkpoint.

---

## 3. Gap Analysis: This Repo vs. The Article

### 3.1 What `chat-agents` already does well

| # | Strength | Evidence | Why it matters |
| :-- | :--- | :--- | :--- |
| 1 | Prompt versioning with per-request overrides | `apps/api/app/services/prompt_registry.py:14-131` + `apps/api/prompts/active.yaml` + `ResearchRequest.prompt_versions` | Chassis of a real A/B experiment framework — Souza has no equivalent |
| 2 | Rich SSE event taxonomy (11 event types) | `apps/api/app/streaming/events.py` | Product-grade events: `reflection_logged`, `compression_triggered`, `subagent_started/completed`, `file_saved` |
| 3 | Chunk mapper is well tested (27 unit tests) | `apps/api/tests/unit/test_chunk_mapper.py` | Covers compression detection, dedup, Overwrite wrapper, non-string files |
| 4 | Dual-LLM cost optimization | `apps/api/app/services/agent_factory.py:11` using `get_fast_llm()` for subagents | Souza uses one model throughout |
| 5 | Fallback draft recovery | `apps/api/app/routers/research.py:87-101` reads `draft.md` from the VFS if streamed report < 200 chars | Pragmatic answer to a failure Souza doesn't acknowledge |
| 6 | `think_tool` → `reflection_logged` SSE pattern | commit `f5eee5d`, `apps/api/app/tools/think_tool.py:4` | Exemplary extension of the typed contract on both sides |

### 3.2 What is missing (article as yardstick)

| Dimension | Article | This repo | Evidence |
| :--- | :--- | :--- | :--- |
| Checkpoint store | Postgres | **SQLite file** | `apps/api/app/stores/memory_store.py:18` — AsyncSqliteSaver at `./data/checkpoints.sqlite` |
| Semantic memory | mem0 + pgvector, persistent | **InMemoryStore** — resets on restart | `apps/api/app/stores/memory_store.py:10`; `memory_updated` SSE event defined but **never emitted** |
| Guardrails | Input/output nodes with PII + injection + LLM judge | **None** | No middleware beyond CORS in `main.py` |
| Auth | JWT with session | **None** | Anyone can call `/research` |
| Rate limiting | Per-endpoint via middleware | **None** | — |
| Tracing | Langfuse | **None** | stdlib logging only |
| Metrics | Prometheus (duration, tokens, tool counts) | **None** | — |
| Retries / circuit breakers | `with_retry` on model, MCP reconnect | **None** | single Tavily failure kills the stream |
| Timeouts | (implied via infra) | **None** | `/research` can hang indefinitely |
| Context overflow control | Two-stage (truncate then summarize) | **Partial (observed, not controlled)** | Deep Agents handles `VFS_OFFLOAD_THRESHOLD_TOKENS=20_000` internally; you observe compression but can't steer it |
| MCP | Multi-server SSE session manager | **None** | — |
| HITL | Not covered | **None** | client-side abort only, via `AbortController` in `apps/web/lib/useResearchStream.ts:101` |
| Durable execution | None | **None** | — |
| Sandboxed code exec | None | **None** | — |
| Supervisor pattern | Explicit in multi-agent template | **Implicit** via Deep Agents `task` tool only | no `langgraph-supervisor`; no explicit routing control |
| Evals | LLM-as-judge over Langfuse traces | **None** | — |

### 3.3 Latent bugs surfaced during the audit

1. **`memory_updated` is half-wired.** Declared in `SSEEventMap` (`apps/web/lib/types.ts`) and dispatched by the reducer, but never emitted by the backend.
2. **Error terminates stream without `stream_end`.** `apps/api/app/routers/research.py:115-120` emits an `error` event then exits; the frontend reducer's `done` state is never reached, leaving the UI stuck in `"streaming"` unless the client's state machine explicitly treats `error` as terminal.
3. **No timeout on `/research`.** A hung Tavily call ties up the process indefinitely.

---

## 4. Ecosystem Survey (April 2026)

Legend: ✓ built-in · ◐ partial/via adapter · — not provided.

| Framework | Multi-agent | Tools | MCP | HITL | Sandbox | Stream | State/Mem | Obs/Trace | Guardrails | Deploy |
| :--- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| **LangGraph + supervisor** | ✓ | ✓ | ◐ via `langchain-mcp-adapters` | ✓ `interrupt` | — | ✓ | ✓ | ✓ LangSmith | ◐ | ◐ |
| **Deep Agents** (what you use) | ✓ | ✓ | ✓ (v0.5) | ✓ | ✓ (v0.5) | ✓ | ✓ | ✓ | ◐ | ✓ Deploy |
| **OpenAI Agents SDK** | ✓ handoffs | ✓ | ✓ | ✓ approvals | ✓ | ✓ | ✓ Sessions | ✓ | ✓ tripwires | ◐ (+Temporal ✓) |
| **Claude Agent SDK** | ◐ subagents | ✓ | ✓ deepest | ✓ hooks + `permission_mode` | ✓ OS sandbox | ✓ | ✓ | ✓ | ✓ | ✓ Managed |
| **AutoGen / MS Agent Framework 1.0** | ✓ | ✓ | ◐ | ◐ | ✓ Docker/Jupyter | ✓ | ◐ | ✓ OTel | ◐ | ◐ |
| **CrewAI** | ✓ Crews/Flows | ✓ | ◐ | ✓ | — | ◐ | ✓ layered | ✓ AMP | ✓ | ✓ AMP |
| **PydanticAI** | ◐ | ✓ | ✓ | ✓ approvals | — | ✓ | ◐ | ✓ Logfire | ◐ | — |
| **LlamaIndex AgentWorkflow** | ✓ | ✓ | ✓ | ◐ | ◐ | ✓ | ✓ | ✓ | ◐ | ◐ |
| **Smolagents** | ◐ | ✓ code-as-action | ✓ | — | ✓ E2B/Modal | ◐ | — | ◐ | — | — |
| **Letta** (memory specialist) | ◐ | ✓ | ✓ | ◐ | ◐ | ✓ | ✓✓ | ✓ | ◐ | ✓ service |
| **Mastra** (TS) | ✓ | ✓ | ✓ | ✓ | ◐ | ✓ | ✓ | ✓ OTel | ✓ | ◐ |
| **Inngest AgentKit** (TS, durable) | ✓ Networks | ✓ | ✓ | ✓ | — | ✓ `useAgent` | ✓ durable | ✓ | ◐ | ✓ |
| **Temporal + LLM SDK** | ◐ | ◐ | — | ✓ | — | ◐ | ✓✓ | ✓ | ◐ | ✓✓ |
| **MetaGPT** | ✓ roles | ◐ | — | — | — | — | ◐ | — | — | — |

### 4.1 Where each pulls ahead

- **LangGraph** — graph-level control, time-travel debugging, the `interrupt()` primitive.
- **Deep Agents v0.5** (March 2026) — LangGraph with the opinions baked in; now native sandbox + async subagents.
- **OpenAI Agents SDK** — `tripwires` for guardrails, cleanest tracing dashboard.
- **Claude Agent SDK** — deepest MCP, real OS sandbox, `PreToolUse`/`PostToolUse` hooks are the best-shaped HITL primitive in the ecosystem.
- **Microsoft Agent Framework** — Azure-native, OTel-first observability (AutoGen proper is now in maintenance).
- **CrewAI** — role-based DX, production memory layers, AMP platform.
- **PydanticAI** — type safety at the boundary, Logfire cost tracking.
- **LlamaIndex** — RAG-native multi-agent.
- **Smolagents** — "code as action" efficiency + multi-sandbox options.
- **Letta** — stateful agents as services, memory as primary object.
- **Mastra** — TypeScript-first with Node-native ergonomics.
- **Inngest AgentKit** — durable execution + real-time streaming in one.
- **Temporal** — the reliability substrate under everything else.

### 4.2 Where Souza's stack sits

Same bones as this repo — FastAPI + LangGraph + SSE — with Langfuse/Prometheus observability, Postgres checkpointing instead of SQLite, mem0 for per-user memory, and an opinionated guardrail layer. **Essentially the chat-agents repo's bigger cousin.**

### 4.3 The 2026 inflection point

A split between **graph-runtime** harnesses (LangGraph, AutoGen, LlamaIndex — you own the skeleton) and **managed-runtime** harnesses (Claude Managed Agents, Deep Agents Deploy, CrewAI AMP — vendor owns it). Managed runtimes take over sandboxing, scaling, and durable execution. The question for the next 12 months is whether `chat-agents` is building a self-owned LangGraph harness *à la* Souza, or gradually outsourcing the skeleton to `deepagents` + Deep Agents Deploy while keeping only prompts, tools, and domain logic in-repo.

---

## 5. Phased Proposal

Each phase is independently valuable and can be re-ordered based on which pain bites first.

### Phase 0 — Close latent bugs (half a day)

1. **Always emit `stream_end`** in the `finally` of the SSE generator at `apps/api/app/routers/research.py:115-120`, even on error. Attach the error to the payload.
2. **Either emit or remove `memory_updated`.** Ship a consistent contract.
3. **Add `asyncio.timeout(settings.RESEARCH_TIMEOUT_S)`** around the `astream` loop.

### Phase 1 — Observability & budget (1–2 days)

4. **Structured logging.** Replace stdlib format with `structlog` + a context middleware binding `thread_id` / `request_id` / (future) `user_id`.
5. **LangSmith tracing.** Set `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_PROJECT=chat-agents-dev`. Cheapest ROI — do it before Langfuse, since the stack is already LangChain-native.
6. **Token budget guard.** Wrap `agent.astream` with a counter summing `usage.input_tokens + output_tokens` per chunk; abort with `max_tokens_exceeded` when over budget. Emit a typed SSE `budget_exceeded` event.
7. **Prometheus** — optional now, mandatory before prod. `prometheus-fastapi-instrumentator` for HTTP metrics; custom counters for `tool_invocations_total{tool,status}` and `tokens_used_total{model,agent}`.

### Phase 2 — Guardrails & HITL (3–5 days)

8. **Adopt the factory-guard pattern.** `apps/api/app/guardrails/` with `input_guardrail.py` (prompt-injection + PII detection) and `output_guardrail.py` (LLM-as-judge reusing `get_fast_llm()`). Wrap the Deep Agents graph in a parent `StateGraph` that puts guards at the boundary. **Fail-open.**
9. **Wire `interrupt()` for high-risk tools.** Split tools into `auto_tools` (Tavily, think_tool) and `gated_tools` (mail, external writes, money, published artifacts). Gated tools call `interrupt(...)` with a typed payload; the router surfaces it as a new SSE event `approval_required`. See §6 for the pattern.
10. **Resumable SSE.** Add `POST /research/resume` that accepts `{thread_id, decision}` and calls `agent.invoke(Command(resume=decision), config)`. The existing thread-ID plumbing makes this additive.

### Phase 3 — Supervisor + MCP + code execution (1–2 weeks)

11. **Explicit supervisor.** Migrate from Deep Agents' implicit `task`-tool routing to `langgraph-supervisor`'s `create_supervisor()`. Deterministic routing you can test, subagent discoverability, ability to mix Deep Agent subagents with plain tool-ReAct subagents under one supervisor. Keep Deep Agents as one kind of subagent, not the whole chassis.
12. **MCP client.** `langchain-mcp-adapters` (`MultiServerMCPClient`) for stdio + HTTP MCP servers from settings; merge tools into each subagent's tool list at compile time. Reconnect-on-`ClosedResourceError`. Emit `mcp_status` SSE event.
13. **Sandboxed code execution.** Two tiers: (a) dev — `smolagents.LocalPythonExecutor` (not-a-security-boundary). (b) prod — E2B, Modal, or Daytona. Expose as `python_exec` tool with its own `interrupt()` gate. Mirror Claude Agent SDK's `permission_mode` model.

### Phase 4 — Durability, evals, managed deployment (own-or-outsource decision)

14. **Durable execution.** If a `/research` run can exceed 5 minutes or involve external side effects, wrap the top-level entry in Temporal or Inngest.
15. **Evals.** Auto-discovered markdown metric files (`apps/api/evals/metrics/*.md`), each defining an LLM-as-judge rubric. Run nightly against a held-out question set; push scores to LangSmith. Fail the build on core-metric regressions > X%.
16. **Deployment decision.** (a) Finish the self-owned harness with Postgres + Docker Compose (Souza's path), or (b) move to `deepagents` v0.5 + Deep Agents Deploy and keep only prompts + tools + SSE contract in-repo.

### 5.1 Recommended starting order

Phase 0 → Phase 1 → pick **one** of Phase 2 (HITL) or Phase 3 (MCP) based on product pressure. Phase 4 waits for real usage data.

---

## 6. Code Sketches for the Critical Primitives

Shape-only sketches showing how each primitive integrates with this repo's existing SSE / prompt / chunk-mapper contract.

### 6.1 HITL `interrupt()` as an SSE event

```python
# apps/api/app/tools/gated.py
from langgraph.types import interrupt
from langchain_core.tools import tool

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send email — requires human approval."""
    decision = interrupt({
        "action": "send_email",
        "to": to, "subject": subject, "body": body,
        "reason": "Approve before sending?",
    })
    if decision.get("action") != "approve":
        return "cancelled by user"
    # ... actual send, using decision overrides if any
    return f"sent to {decision.get('to', to)}"
```

```python
# apps/api/app/streaming/events.py — new factory
def approval_required(payload: dict) -> dict:
    return {"event": "approval_required", "data": payload}
```

```python
# apps/api/app/streaming/chunk_mapper.py — detect __interrupt__ in "values" mode
if isinstance(chunk, dict) and "__interrupt__" in chunk:
    for intr in chunk["__interrupt__"]:
        yield approval_required(intr.value)
```

```python
# apps/api/app/routers/research.py — resume endpoint
@router.post("/research/resume")
async def resume(req: ResumeRequest, agent: Agent = Depends(...)):
    config = {"configurable": {"thread_id": req.thread_id}}
    return EventSourceResponse(stream_resume(agent, req.decision, config))

async def stream_resume(agent, decision, config):
    async for mode, chunk in agent.astream(
        Command(resume=decision), config=config, stream_mode=...
    ):
        ...  # reuse the same ChunkMapper
```

Frontend: `useResearchStream` gains an `approval` sub-state and a `POST /api/research/resume` caller. The existing `AbortController` stays (full cancel); `interrupt` is the pause-and-wait path.

### 6.2 Supervisor over Deep Agents

```python
# apps/api/app/services/agent_factory.py
from langgraph_supervisor import create_supervisor
from deepagents import create_deep_agent

def build_research_agent(prompts):
    researcher = create_deep_agent(
        name="researcher",
        model=get_fast_llm(),
        tools=[internet_search, think_tool],
        prompt=prompts.researcher,
    )
    critic = create_deep_agent(
        name="critic", model=get_fast_llm(), tools=[], prompt=prompts.critic
    )
    return create_supervisor(
        [researcher, critic],
        model=get_llm(),
        prompt=prompts.main,
        output_mode="last_message",   # keeps chunk mapper simple
    ).compile(checkpointer=checkpointer, store=store)
```

Every SSE event in `events.py` keeps working — supervisor handoffs become `subagent_started`/`subagent_completed` naturally because the supervisor routes via tool calls.

### 6.3 MCP adapter

```python
# apps/api/app/services/mcp_client.py
from langchain_mcp_adapters.client import MultiServerMCPClient

async def get_mcp_tools(settings) -> list[Tool]:
    # settings.MCP_SERVERS: {"name": {"url": ..., "transport": "sse"}}
    client = MultiServerMCPClient(settings.MCP_SERVERS)
    try:
        return await client.get_tools()
    except Exception as e:
        logger.warning(f"[mcp] degraded: {e}")
        return []
```

Merged into each subagent's tool list at `build_research_agent()` time. Emit an `mcp_status` SSE event once per stream so the UI can show a chip per server.

### 6.4 Sandboxed code execution

```python
# apps/api/app/tools/python_exec.py
from e2b import Sandbox           # or modal, daytona
from langchain_core.tools import tool
from langgraph.types import interrupt

@tool
async def python_exec(code: str) -> str:
    """Execute Python in an isolated sandbox."""
    decision = interrupt({"action": "python_exec", "code": code, "reason": "Approve?"})
    if decision.get("action") != "approve":
        return "cancelled"
    async with Sandbox(template="base", timeout=30) as sbx:
        result = await sbx.run_code(decision.get("code", code))
        return result.text[:8000]
```

Gated by `interrupt()` in dev; gated by a `permission_mode` setting (auto / require_approval / deny) in prod. Same shape as Claude Agent SDK's hook model, which is the best ecosystem reference.

---

## 7. Decision Points (answer these before the first PR)

### 7.1 Harness ownership stance

| Option | What you build | What you outsource | Good when |
| :--- | :--- | :--- | :--- |
| **Self-owned** (Souza's path) | Postgres + Langfuse + Prometheus + Docker Compose + your guardrails | Nothing | Regulatory / on-prem / cost-sensitive / you want full control |
| **Outsourced** | Prompts + tools + SSE contract + frontend | Deep Agents v0.5 + Deep Agents Deploy OR Claude Managed Agents | Small team / speed-to-market / willing to accept vendor lock-in |
| **Hybrid** | Prompts + tools + SSE + *some* guardrails | LangSmith tracing + E2B sandbox + MCP servers | Most teams — lets you swap pieces later |

### 7.2 Target deployment

- **Single-instance dev** → skip auth + rate limiting for now, prioritize tracing + HITL.
- **Multi-tenant SaaS** → auth + per-tenant rate limiting become Phase 1 must-haves.
- **On-prem enterprise** → MCP + sandbox + durable execution take precedence over tracing.

### 7.3 Which pain bites first

| Symptom | Phase to run first |
| :--- | :--- |
| "I can't debug prod stalls" | Phase 1 (tracing) |
| "I'm afraid to let it call real APIs" | Phase 2 (HITL) |
| "It needs to talk to our internal tools" | Phase 3 (MCP) |
| "A run occasionally takes 20 minutes and fails halfway" | Phase 4 (durable execution) |

---

## 8. Recommended Next PR

**Phase 0 + Phase 1 bundled as one PR.** Rationale:

- Phase 0 fixes three real bugs (missing `stream_end`, half-wired `memory_updated`, no timeout) — zero regression risk, immediate user-facing correctness improvement.
- Phase 1 adds structured logging + LangSmith tracing + token budget — immediate operational ROI, and both are prerequisites for every later phase (you can't debug Phase 2's `interrupt()` flow without tracing, and you can't cost-cap Phase 3's MCP tools without the token counter).

**Deliverables for the PR**:
1. `finally` block + error-aware `stream_end` in `apps/api/app/routers/research.py`.
2. Decision on `memory_updated` (emit it from the LangGraph store write listener, or delete it from `SSEEventMap` and the frontend reducer).
3. `asyncio.timeout(settings.RESEARCH_TIMEOUT_S)` around the `astream` loop.
4. `structlog` + context middleware; replace all module loggers.
5. LangSmith env vars documented in `apps/api/.env.example` and `CONTRIBUTING.md`.
6. Token budget counter in the SSE generator; new `budget_exceeded` SSE event type, wired on both sides per the contract rule in `CLAUDE.md`.
7. Tests: one unit test per new behavior (timeout, budget counter, error → `stream_end`), one e2e test that a dropped Tavily call produces `error` *and* `stream_end`.

**Explicitly out of scope** for this PR: auth, rate limiting, Langfuse, Prometheus, guardrails, HITL, MCP, supervisor, sandbox, evals. Each of those gets its own PR after this foundation lands.

---

## 9. References

- [Building a Production-Ready AI Agent Harness — apssouza22, dev.to](https://dev.to/apssouza22/building-a-production-ready-ai-agent-harness-2570)
- [LangGraph 1.0 — LangChain Changelog](https://changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available)
- [LangGraph interrupts — LangChain Docs](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [langchain-ai/langgraph-supervisor-py](https://github.com/langchain-ai/langgraph-supervisor-py)
- [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents)
- [Deep Agents v0.5 — LangChain Blog](https://blog.langchain.com/deep-agents-v0-5/)
- [OpenAI Agents SDK — Guardrails](https://openai.github.io/openai-agents-python/guardrails/)
- [Claude Agent SDK hooks — Claude API Docs](https://platform.claude.com/docs/en/agent-sdk/hooks)
- [Claude Managed Agents — The New Stack](https://thenewstack.io/with-claude-managed-agents-anthropic-wants-to-run-your-ai-agents-for-you/)
- [Microsoft Agent Framework 1.0 — DevBlogs](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/)
- [CrewAI Documentation](https://docs.crewai.com/)
- [PydanticAI](https://ai.pydantic.dev/)
- [LlamaIndex AgentWorkflow](https://www.llamaindex.ai/workflows)
- [HuggingFace smolagents blog](https://huggingface.co/blog/smolagents)
- [Letta (formerly MemGPT)](https://github.com/letta-ai/letta)
- [Mastra TypeScript AI Agent Framework](https://mastra.ai/)
- [Inngest AgentKit `useAgent`](https://www.inngest.com/blog/agentkit-useagent-realtime-hook)
- [OpenAI Agents SDK + Temporal integration](https://temporal.io/blog/announcing-openai-agents-sdk-integration)
