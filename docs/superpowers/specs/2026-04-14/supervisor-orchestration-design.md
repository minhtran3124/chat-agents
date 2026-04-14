# Supervisor Orchestration — Design Spec

**Date:** 2026-04-14
**Status:** Draft (awaiting review)
**Scope:** Orchestration keystone (axis A). Model & tool registries and the declarative `AgentSpec` are included as API surfaces baked into this spec. TTFT measurement (axis D) and evaluation harness (axis E) are deliberately deferred to separate specs.
**Audience:** Engineers implementing the backend redesign on `apps/api/`.

---

## 1. TL;DR

- Replace the current single-pipeline `POST /research` with a **supervisor-routed** graph. A cheap LLM-backed classifier picks one of six intents and dispatches to a specialist agent.
- Six specialists: `chat`, `research`, `deep-research`, `summarize`, `code`, `planner`. Only `deep-research` uses the existing `deepagents.create_deep_agent(...)` pipeline. The other five are lightweight single-loop ReAct-style agents.
- Introduce three collaborating registries: **`ModelRegistry`** (per-role LLM selection, OpenAI primary), **`ToolRegistry`** (decorator auto-discovery), and a Pydantic **`AgentSpec`** bound in code. The existing `PromptRegistry` is reused unchanged.
- One new SSE event: `intent_classified`. All other events are preserved. Subgraph-emitted events (`todo_updated`, `file_saved`, `subagent_started/completed`) continue to work for `deep-research` via LangGraph's `subgraphs=True` streaming.
- `POST /chat` is the new unified routed endpoint. `POST /research` is preserved as a **power-user bypass** that pins `intent="deep-research"` and skips the classifier, giving the fastest path when the caller already knows the intent.
- **Primary provider is OpenAI.** Anthropic and Google are optional alternatives, selectable per-role via `models.yaml` or env override with no code change.

---

## 2. Goals & Non-Goals

### Goals (in scope)

1. Supervisor topology with LLM-backed intent classifier and conditional edges to six specialists.
2. Declarative `AgentSpec` (code-resident) binding each specialist to registry keys for model, tools, and prompt.
3. `ModelRegistry` backed by `models.yaml` with per-role env overrides. OpenAI default for all three roles (`classifier`, `fast`, `main`).
4. `ToolRegistry` with decorator-based auto-discovery from `app/tools/`.
5. New `POST /chat` endpoint; preserve `POST /research` as the deep-research bypass.
6. One new SSE event: `intent_classified`. Update backend emitter, frontend `SSEEventMap`, and `useResearchStream` hook.
7. LangGraph-native subgraph composition for `deep-research` (wraps existing `create_deep_agent(...)`).
8. Multi-turn intent stickiness: classifier reads last user message + `current_intent`.
9. Tiered error handling reusing the existing `error(..., recoverable=True|False)` flag. No new error events.
10. Testing parity: every build function has unit tests; full SSE flow is covered for at least `chat`, `summarize`, and `deep-research`.

### Non-goals (out of scope — deferred)

- TTFT metrics, histograms, latency dashboards — Spec D.
- Red-team suites, LLM-as-judge scoring, regression harness — Spec E.
- Bypass endpoints for `summarize`, `code`, `planner`. Trivial to add later once demand is established.
- Retry-with-backoff at any layer. Added only when telemetry shows specific retry-worthy failures.
- Per-request `intent_override` in the payload. Clients that know the intent should use the `/research` bypass (for `deep-research`) until more bypasses are added.
- Human-in-the-loop interrupts (`interrupt_before`, plan-approval mode). Not needed for v1.
- A `needs_clarification` specialist. Silent fallback to `chat` is the v1 behavior for low-confidence classifications.

---

## 3. Architecture Overview

```
POST /chat  { question, thread_id?, prompt_versions? }
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Outer LangGraph  (app/agents/supervisor_graph.py)              │
│                                                                 │
│    START → classifier → (add_conditional_edges on intent) →     │
│                                                                 │
│    ├─→ chat           (ReAct, no tools)                         │
│    ├─→ research       (ReAct + web_search, fetch_url)           │
│    ├─→ deep_research  (EXISTING create_deep_agent, as subgraph) │
│    ├─→ summarize      (ReAct, no tools)                         │
│    ├─→ code           (ReAct + repo_search, fetch_url)          │
│    └─→ planner        (ReAct, no tools)                         │
│                                                                 │
│    each specialist → END                                        │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼  (router streams with subgraphs=True)
SSE: stream_start · intent_classified · text_delta · … · stream_end
     (todo_updated / file_saved / subagent_* only during deep-research)
```

`POST /research` is the same graph, entered through a bypass node that writes `current_intent="deep-research"`, emits `intent_classified(fallback_used=false, confidence=1.0)`, and jumps to `deep_research`. No classifier call is made, giving identical latency to today's `/research`.

### Why a classifier node, not a supervisor-agent

We considered `langgraph-supervisor` (supervisor-as-agent) and a hybrid `Command(goto=...)` pattern. We chose classifier-node-with-conditional-edges because:

- **TTFT-friendly.** One `gpt-4o-mini` call with structured output (~150–300 ms), then the specialist streams directly to the client. A supervisor-agent adds an extra LLM hop on every request.
- **Testable as a pure function.** The classifier is `(messages, current_intent) → (intent, confidence)`. Unit tests use fixture messages and a mocked LLM.
- **Cheap and predictable.** Haiku-class cost per request for routing. No reasoning tokens burned on decisions the graph can enforce declaratively.
- **Simple termination.** Each request walks the graph at most twice (classifier, then one specialist). No loop, no escalation, no max-hop guard needed.

---

## 4. Intent Taxonomy

Six intents. The classifier's structured output is exactly one of these six strings, plus a confidence score.

| Intent         | Tools                       | Model role → default model    | When the classifier picks it                                                               |
| :------------- | :-------------------------- | :---------------------------- | :----------------------------------------------------------------------------------------- |
| `chat`         | —                           | `fast` → `gpt-4o-mini`        | Casual Q&A, greetings, short factual questions with known answers. Also the **silent fallback** for low-confidence classifications. |
| `research`     | `web_search`, `fetch_url`   | `main` → `gpt-4o`             | Needs fresh info / citations, but fits in one agent loop (≤ ~3 searches).                  |
| `deep-research`| deepagents internals + `web_search` | `main` + `fast` → `gpt-4o` + `gpt-4o-mini` | Multi-phase investigation; compound questions; user explicitly asks for a "deep dive", "comprehensive", or "full report". |
| `summarize`    | —                           | `fast` → `gpt-4o-mini`        | User provides content and asks for reduction / extraction / tldr.                          |
| `code`         | `repo_search`, `fetch_url`  | `main` → `gpt-4o`             | Code review, codebase Q&A, design critique on a snippet.                                   |
| `planner`      | —                           | `fast` → `gpt-4o-mini`        | User asks for a checklist, plan, roadmap, or step-by-step breakdown.                       |
| *(classifier)* | —                           | `classifier` → `gpt-4o-mini` (with `response_format=json_schema`) | Always runs first on `/chat`; never runs on `/research`. |

**Confidence threshold:** `confidence < 0.55` → silent fallback to `chat`.
**Intent-stickiness rule:** if classifier returns the same intent as `current_intent` with `confidence ≥ 0.40`, stick. This handles "tell me more" and continuation follow-ups on any specialist.

### Worked routing examples

| User message (with `current_intent`)                                      | Expected intent | Reason                                       |
| :------------------------------------------------------------------------ | :-------------- | :------------------------------------------- |
| "hi!" (none)                                                              | `chat`          | Greeting.                                    |
| "What's the latest on the 2026 EU AI Act amendments?" (none)              | `research`      | Needs fresh info, fits one loop.             |
| "Give me a full report on every major LLM released in 2026." (none)       | `deep-research` | Multi-phase; compound; explicit breadth.     |
| "Summarize this transcript: <...>" (none)                                 | `summarize`     | Content supplied, reduction requested.       |
| "Review this function for bugs: `def x(): …`" (none)                      | `code`          | Code content + review verb.                  |
| "Break that down into weekly milestones." (current=`research`)            | `planner`       | Explicit planning verb overrides stickiness. |
| "Tell me more." (current=`research`)                                      | `research`      | Stickiness; low-entropy follow-up.           |
| "blah asdf qwerty" (none)                                                 | `chat`          | Low confidence → silent fallback.            |

---

## 5. Registries + `AgentSpec`

### 5.1 `ModelRegistry`

**Source:** `apps/api/models.yaml` (new file at the api app root, same level as `prompts/`).
**Mechanism:** YAML defaults + env override per role. Env wins.
**Per-role fields:** `provider`, `model`, `temperature`, `streaming`, plus provider-specific passthrough (`response_format` on OpenAI, etc.).

```yaml
# apps/api/models.yaml
# Primary provider: OpenAI. Swap any role by editing this file
# or by setting the corresponding env var (CLASSIFIER_MODEL, FAST_MODEL, MAIN_MODEL).

classifier:
  provider: openai
  model: gpt-4o-mini
  temperature: 0.0
  streaming: false
  response_format: json_schema   # OpenAI-specific; ignored on other providers

fast:
  provider: openai
  model: gpt-4o-mini
  temperature: 0.3
  streaming: true

main:
  provider: openai
  model: gpt-4o
  temperature: 0.7
  streaming: true

# Optional provider alternatives (commented out; copy into a role to switch):
# main:
#   provider: anthropic
#   model: claude-sonnet-4-6
# fast:
#   provider: google
#   model: gemini-1.5-flash
```

**Registry API:**

```python
class ModelSpec(BaseModel):
    provider: Literal["openai", "anthropic", "google"]
    model: str
    temperature: float = 0.7
    streaming: bool = True
    response_format: str | None = None   # OpenAI-only; ignored elsewhere

class ModelRegistry:
    def __init__(self, yaml_path: Path, env: Mapping[str, str]): ...
    def reload(self) -> None: ...
    def get(self, role: str) -> ModelSpec: ...
    def build(self, role: str) -> BaseChatModel:
        """Return a configured LangChain chat model, caching by role."""
```

**Env override naming:** `<ROLE>_MODEL` overrides the `model` field only. Provider and other fields stay from YAML. Examples:

- `CLASSIFIER_MODEL=gpt-4o-mini` → same as default.
- `MAIN_MODEL=claude-sonnet-4-6` **AND** `MAIN_PROVIDER=anthropic` → swap provider + model together (two vars; keeps one-env-per-scalar simple).

Construct in lifespan:

```python
# app/main.py
model_registry = ModelRegistry(
    yaml_path=Path(__file__).parents[1] / "models.yaml",
    env=os.environ,
)
```

### 5.2 `ToolRegistry`

**Mechanism:** decorator-based auto-discovery. Every tool module in `app/tools/*.py` uses `@register_tool("name")`. `import app.tools` from the lifespan triggers registration via the package `__init__.py`'s explicit imports (no wildcard `import *`).

```python
# app/tools/registry.py
class ToolRegistry:
    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[BaseTool], BaseTool]:
        def deco(t: BaseTool) -> BaseTool:
            if name in cls._tools:
                raise RuntimeError(f"Tool '{name}' already registered")
            cls._tools[name] = t
            return t
        return deco

    @classmethod
    def get(cls, name: str) -> BaseTool: ...
    @classmethod
    def get_many(cls, names: list[str]) -> list[BaseTool]: ...

register_tool = ToolRegistry.register
```

**Initial tools:**

- `web_search` — existing Tavily wrapper, moved from `services/search_tool.py` to `app/tools/web_search.py` and decorated.
- `fetch_url` — **new**. `httpx.AsyncClient` GET, 10 s timeout, text response capped at 50 KB.
- `repo_search` — **new**. Git-aware grep over the current working tree. Rooted at repo root, honors `.gitignore`.

Tool errors are caught inside the wrapper: the tool returns `{"error": str(e)}` rather than raising. See §10.

### 5.3 `AgentSpec` + bindings

`AgentSpec` is a Pydantic model in `app/agents/specs.py`. One instance per specialist. Strong typing; easy to search; safe for refactors. Registries resolve string keys at build time.

```python
class AgentSpec(BaseModel):
    name: Literal["chat","research","deep-research","summarize","code","planner"]
    model_role: str                         # key into ModelRegistry
    tools: list[str] = []                   # keys into ToolRegistry
    prompt_name: str                        # key into PromptRegistry
    subagents: list["AgentSpec"] = []       # deep-research only

REGISTERED_SPECS: list[AgentSpec] = [
    AgentSpec(name="chat", model_role="fast", prompt_name="chat"),
    AgentSpec(name="research", model_role="main", tools=["web_search","fetch_url"], prompt_name="research"),
    AgentSpec(
        name="deep-research",
        model_role="main",
        tools=["web_search"],
        prompt_name="main",                # existing 'main' prompt
        subagents=[
            AgentSpec(name="researcher", model_role="fast", tools=["web_search"], prompt_name="researcher"),
            AgentSpec(name="critic",     model_role="fast", tools=[],             prompt_name="critic"),
        ],
    ),
    AgentSpec(name="summarize", model_role="fast", prompt_name="summarize"),
    AgentSpec(name="code",      model_role="main", tools=["repo_search","fetch_url"], prompt_name="code"),
    AgentSpec(name="planner",   model_role="fast", prompt_name="planner"),
]
```

`subagents` is a nested list only for `deep-research`. For the other five, it is empty — they are single-loop ReAct agents.

---

## 6. File Layout

```
apps/api/
├── app/
│   ├── agents/                       # NEW
│   │   ├── __init__.py
│   │   ├── specs.py                  # AgentSpec + REGISTERED_SPECS
│   │   ├── classifier.py             # classify(messages, current_intent) -> ClassifierResult
│   │   ├── supervisor_graph.py       # build_supervisor_graph(settings, registries)
│   │   └── builders/
│   │       ├── __init__.py
│   │       ├── react.py              # build_react_agent(spec, reg) — shared by chat/research/summarize/code/planner
│   │       └── deep_research.py      # wraps existing create_deep_agent(...)
│   ├── models/                       # NEW
│   │   ├── __init__.py
│   │   └── registry.py               # ModelRegistry + ModelSpec
│   ├── tools/                        # NEW
│   │   ├── __init__.py               # explicit imports trigger @register_tool
│   │   ├── registry.py               # ToolRegistry + @register_tool decorator
│   │   ├── web_search.py             # Tavily (moved from services/search_tool.py)
│   │   ├── fetch_url.py              # NEW
│   │   └── repo_search.py            # NEW
│   ├── schemas/
│   │   ├── research.py               # existing (add intent_override? NO — out of scope)
│   │   ├── chat.py                   # NEW: ChatRequest (same fields as ResearchRequest)
│   │   └── routing.py                # NEW: ClassifierResult, RoutingEvent
│   ├── routers/
│   │   ├── research.py               # refactored to call _run_graph(force_intent="deep-research")
│   │   └── chat.py                   # NEW: calls _run_graph(force_intent=None)
│   ├── streaming/
│   │   ├── events.py                 # + intent_classified() factory
│   │   └── chunk_mapper.py           # add intent_classified passthrough; support (namespace, mode, chunk) 3-tuple
│   ├── services/
│   │   ├── agent_factory.py          # kept as thin shim around builders/deep_research.py for back-compat
│   │   ├── llm_factory.py            # DELETED — replaced by ModelRegistry
│   │   ├── search_tool.py            # DELETED — replaced by app/tools/web_search.py
│   │   └── prompt_registry.py        # unchanged
│   ├── stores/memory_store.py        # unchanged
│   └── main.py                       # lifespan builds ModelRegistry, imports app.tools, loads PromptRegistry
├── prompts/
│   ├── active.yaml                   # + entries for classifier, chat, summarize, code, planner
│   ├── classifier/v1.md              # NEW
│   ├── chat/v1.md                    # NEW
│   ├── summarize/v1.md               # NEW
│   ├── code/v1.md                    # NEW
│   ├── planner/v1.md                 # NEW
│   ├── research/v1.md                # NEW (simple, single-loop)
│   ├── main/v1.md                    # existing (deep-research)
│   ├── researcher/v1.md              # existing
│   └── critic/v1.md                  # existing
├── models.yaml                       # NEW
└── tests/
    ├── unit/
    │   ├── test_model_registry.py    # NEW
    │   ├── test_tool_registry.py     # NEW
    │   ├── test_classifier.py        # NEW
    │   ├── test_agent_specs.py       # NEW
    │   └── test_prompt_registry.py   # existing
    ├── integration/
    │   ├── test_supervisor_graph.py  # NEW: all 6 specialists compile; routing edges exist
    │   ├── test_chat_endpoint.py     # NEW: SSE per intent with mocked LLM + tools
    │   └── test_research_endpoint.py # refactor: now a bypass test
    └── e2e/
        ├── test_chat_chat.py         # NEW: chat intent full SSE
        ├── test_chat_summarize.py    # NEW: summarize intent full SSE
        └── test_deep_research.py     # refactor of existing e2e
```

---

## 7. Graph State

```python
from typing import Annotated, Literal, TypedDict
from langgraph.graph.message import add_messages
import operator

class RoutingEvent(BaseModel):
    turn: int
    intent: str
    confidence: float
    fallback_used: bool
    ts: datetime

class GraphState(TypedDict):
    messages: Annotated[list, add_messages]
    current_intent: Literal["chat","research","deep-research","summarize","code","planner"]
    confidence: float
    fallback_used: bool
    routing_history: Annotated[list[RoutingEvent], operator.add]
```

**Field ownership** (per the pattern in `docs/research-langgraph-agent.md` §3):

| Field             | Writer                      | Reader          |
| :---------------- | :-------------------------- | :-------------- |
| `messages`        | all (via `add_messages`)    | all             |
| `current_intent`  | `classifier` (or bypass)    | all             |
| `confidence`      | `classifier`                | all             |
| `fallback_used`   | `classifier`                | all             |
| `routing_history` | `classifier` (append)       | all             |

---

## 8. Classifier Design

**File:** `app/agents/classifier.py`
**Signature:** `async def classify(messages: list, current_intent: str | None, registry: ModelRegistry) -> ClassifierResult`
**Input to the LLM:** the **last user message only**, plus `current_intent` (if any) passed as a structured hint. Full history is not sent — classifier is cheap, fast, and does not need it.

**Structured output** via OpenAI JSON schema:

```json
{
  "name": "classify_intent",
  "schema": {
    "type": "object",
    "properties": {
      "intent": { "enum": ["chat","research","deep-research","summarize","code","planner"] },
      "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
    },
    "required": ["intent","confidence"]
  }
}
```

For non-OpenAI providers (Anthropic, Google), the registry falls back to a tool-call representation of the same schema (`llm.with_structured_output(ClassifierResult)` via LangChain's provider-agnostic wrapper).

**Fallback logic** — the only place in the graph that branches on the classifier:

```python
async def classifier_node(state: GraphState, reg: ModelRegistry) -> Command:
    try:
        result = await classify(state["messages"], state.get("current_intent"), reg)
    except Exception:
        # Classifier failure: silent fallback
        result = ClassifierResult(intent="chat", confidence=0.0, fallback_used=True)

    intent = result.intent
    if result.confidence < 0.55:
        intent = "chat"
        result = result.model_copy(update={"fallback_used": True})
    elif state.get("current_intent") == result.intent and result.confidence >= 0.40:
        intent = result.intent  # stickiness (no-op)

    event = RoutingEvent(
        turn=len(state.get("routing_history", [])) + 1,
        intent=intent,
        confidence=result.confidence,
        fallback_used=result.fallback_used,
        ts=datetime.now(UTC),
    )
    return Command(
        goto=intent,
        update={
            "current_intent": intent,
            "confidence": result.confidence,
            "fallback_used": result.fallback_used,
            "routing_history": [event],
        },
    )
```

---

## 9. SSE Contract Changes

### Backend — `app/streaming/events.py`

```python
def intent_classified(intent: str, confidence: float, fallback_used: bool) -> dict:
    return _sse("intent_classified", {
        "intent": intent,
        "confidence": confidence,
        "fallback_used": fallback_used,
    })
```

Emitted exactly once per request, **after** the classifier runs, **before** the first `text_delta`. For the `/research` bypass, emitted with `{intent: "deep-research", confidence: 1.0, fallback_used: false}`.

### Backend — `app/streaming/chunk_mapper.py`

- Accept the 3-tuple `(namespace, mode, chunk)` shape from `astream(..., subgraphs=True)`. Current 2-tuple remains supported for the classifier/simple specialists; the 3-tuple is unpacked in the `deep-research` path.
- Surface `intent_classified` from the outer graph's `Command.update` using a small bookkeeping check: when the classifier node emits its `Command`, the router sends the corresponding SSE event before streaming any specialist tokens.
- All other mapping logic (`todo_updated`, `file_saved`, `subagent_started/completed`, `compression_triggered`) is unchanged; it now applies to the `deep-research` subgraph's surfaced events.

### Frontend — `apps/web/lib/types.ts`

```ts
type SSEEventMap = {
  // …existing entries…
  intent_classified: { intent: string; confidence: number; fallback_used: boolean };
};
```

### Frontend — `apps/web/lib/useResearchStream.ts`

- New state field: `routedIntent: string | null`.
- Handler for `intent_classified`: `setRoutedIntent(event.intent)`.
- Dashboard panels already render conditionally; no deeper change required. A small "routed to: X" badge component can render next to the question input.

---

## 10. Endpoints

### `POST /chat` (new)

Payload (same fields as current `/research`):

```python
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    thread_id: str | None = None
    prompt_versions: dict[str, str] | None = None
```

Behavior: call `_run_graph(payload, force_intent=None)`. Supervisor graph runs classifier → specialist → end.

### `POST /research` (preserved bypass)

Payload unchanged (`ResearchRequest`). Behavior: call `_run_graph(payload, force_intent="deep-research")`. No classifier call; `intent_classified` is emitted with confidence=1.0 and fallback_used=false; jumps to the `deep_research` node directly.

### Shared runner

`_run_graph(payload, force_intent)` lives in a new `app/routers/_runner.py` and is called by both endpoints. One generator function, one try/except, one chunk-mapper instance per request.

---

## 11. Config & Settings

### `app/config/settings.py` changes

```python
# Change default provider
LLM_PROVIDER: Literal["openai", "anthropic", "google"] = "openai"  # was "anthropic"
```

Validator update: a provider's API key is required **only if** any role in `models.yaml` points at that provider. Resolution happens after `ModelRegistry` loads, not in `Settings`. Settings now only asserts: *at least one of OPENAI/ANTHROPIC/GOOGLE key is set*; the registry validates role-specific keys at build time and fails fast on app startup if any referenced provider is missing its key.

### `.env` example (required + optional)

```bash
OPENAI_API_KEY=sk-...           # required (primary provider)
TAVILY_API_KEY=tvly-...         # required (web_search tool)
# Optional:
ANTHROPIC_API_KEY=sk-ant-...    # only needed if any role in models.yaml → provider: anthropic
GOOGLE_API_KEY=...              # only needed if any role → provider: google
# Optional per-role overrides:
# CLASSIFIER_MODEL=gpt-4o-mini
# MAIN_MODEL=claude-sonnet-4-6
# MAIN_PROVIDER=anthropic
```

---

## 12. Error Handling

Reuses the existing `error(message, recoverable)` event factory. No new error events.

| Failure                                | Behavior                                                                                             |
| :------------------------------------- | :--------------------------------------------------------------------------------------------------- |
| Classifier LLM error (timeout, parse, rate-limit) | Silent fallback to `chat` intent. Emit `intent_classified(intent="chat", confidence=0.0, fallback_used=true)`. No `error` event. |
| Tool exception (Tavily / fetch_url / repo_search) | Tool wrapper catches and returns `{"error": str(e)}` as the tool response. Emit `error(message=..., recoverable=True)` as a side-channel. Stream continues; agent decides next step. |
| Specialist LLM error mid-stream        | Emit `error(message=..., recoverable=False)`. Close the stream. Existing behavior for `/research` extended to all specialists. |
| `deep-research` subgraph error         | Same as specialist LLM error. Any tokens already emitted are preserved in `final_report` of `stream_end`. |

---

## 13. Testing Strategy

### Unit (new)

- **`test_model_registry.py`**
  - YAML loads correctly; missing keys raise `ValueError`.
  - Env override wins for `model`; provider stays from YAML unless `<ROLE>_PROVIDER` is also set.
  - Mixed providers across roles (`main: openai`, `fast: anthropic`) require both API keys; ValueError when either is missing.
- **`test_tool_registry.py`**
  - `@register_tool` adds; duplicate registration raises.
  - `get_many(["web_search","fetch_url"])` returns the tools in the order requested.
- **`test_classifier.py`**
  - Table of fixture (user_message, current_intent) → expected (intent, confidence). Mock LLM with `FakeListChatModel`.
  - Low-confidence fallback path: confidence=0.30 → intent forced to `chat`, fallback_used=true.
  - Stickiness: current=`research`, classifier=`research` with confidence=0.45 → stays `research`.
  - Exception path: mock LLM raises → `chat` fallback with confidence=0.0.
- **`test_agent_specs.py`**
  - Every `AgentSpec.tools` key resolves in a fresh `ToolRegistry` populated from `app.tools`.
  - Every `AgentSpec.prompt_name` resolves in the `PromptRegistry`.
  - Every `AgentSpec.model_role` resolves in the `ModelRegistry`.

### Integration (new)

- **`test_supervisor_graph.py`**
  - `build_supervisor_graph(...)` returns a compiled graph with all six target nodes and the classifier node.
  - Conditional edges exist from `classifier` to each specialist.
- **`test_chat_endpoint.py`** — one parameterized test per intent, SSE sequence asserted.
- **`test_research_endpoint.py`** — refactored: bypass path skips classifier, emits `intent_classified(intent="deep-research", confidence=1.0, fallback_used=false)`, preserves existing SSE shape.

### E2E smoke (new + refactored)

- `test_chat_chat.py` — `chat` intent, one message, expect `stream_start`, `intent_classified`, ≥1 `text_delta`, `stream_end`.
- `test_chat_summarize.py` — `summarize` intent, one message with a paragraph to summarize.
- `test_deep_research.py` — refactor of the existing deep-research e2e with the new bypass path.

### Regression

- All existing `/research` tests must pass unchanged after the bypass refactor. The SSE sequence adds `intent_classified` exactly once; tests update assertions accordingly.

### Mocking rules (unchanged from `guidelines.md`)

- Never hit real LLM APIs or Tavily in `pytest`. Use `FakeListChatModel` for LLMs and a patched `tavily.TavilyClient` for `web_search`.
- `asyncio_mode = "auto"` is configured; no `@pytest.mark.asyncio` decorator needed.

---

## 14. Rollout Order (for the implementation plan, Spec-next)

The implementation plan will sequence these so the app stays green after each step:

1. **Registries.** `ModelRegistry`, `ToolRegistry`, `AgentSpec`. Wire into `lifespan`. Add tests. No behavioral change — the old agent factory still works.
2. **Tools move.** Relocate Tavily tool into `app/tools/web_search.py` with `@register_tool`. Delete `services/search_tool.py`. Add `fetch_url` and `repo_search`.
3. **Classifier.** `app/agents/classifier.py` + `prompts/classifier/v1.md`. Unit tests.
4. **ReAct builder.** `app/agents/builders/react.py` — one function serves `chat`, `research`, `summarize`, `code`, `planner`. Each prompt added under `prompts/<intent>/v1.md`.
5. **Deep-research builder.** `app/agents/builders/deep_research.py` wraps the existing `create_deep_agent(...)` call with the new `AgentSpec`.
6. **Supervisor graph.** `app/agents/supervisor_graph.py` wires classifier → conditional edges → six specialists → END. Integration tests.
7. **Shared runner.** `app/routers/_runner.py` with `_run_graph(payload, force_intent)`.
8. **`/chat` router.** `app/routers/chat.py` and include in `main.py`.
9. **`/research` refactor.** Router becomes a thin bypass calling `_run_graph(..., force_intent="deep-research")`. Existing tests pass unchanged modulo the `intent_classified` event.
10. **SSE contract + frontend.** `events.py` factory; `chunk_mapper` 3-tuple support; `SSEEventMap`; `useResearchStream` state update; badge component.
11. **Delete `llm_factory.py`** once no callers remain.

Each step is independently reviewable. Step 1 is the foundation; steps 2–5 can be parallelized by sub-PR; step 6 integrates; steps 7–11 wire it up.

---

## 15. Open Questions & Assumptions

### Resolved during brainstorming

- **Supervisor shape.** Classifier-node-with-conditional-edges chosen over `langgraph-supervisor` (extra LLM hop) and `Command` hybrid (termination complexity).
- **Fallback on low confidence.** Silent fallback to `chat`. No user-facing clarify UI in v1.
- **Endpoint strategy.** `/chat` added; `/research` preserved as bypass (power-user + back-compat).
- **Registry shape.** YAML defaults + env overrides for models; decorator auto-discovery for tools; code-resident Pydantic `AgentSpec` for agents.
- **Primary provider.** OpenAI. Anthropic and Google remain first-class alternatives via config.

### Assumptions to verify during implementation

- **LangGraph subgraph streaming.** Assumed that `parent_graph.astream(..., subgraphs=True)` surfaces inner subgraph events (AIMessageChunk, tool calls, state updates) with the same shape `chunk_mapper` currently expects. If the 3-tuple unpacking adds quirks around node-name prefixes, `chunk_mapper` is the single file to adjust.
- **Structured output parity.** OpenAI's `response_format=json_schema` is the reliable path. Anthropic/Google fall back to `with_structured_output(...)` which LangChain routes through tool-calls internally. Both return the same Pydantic model.
- **Classifier latency.** Estimated ~150–300 ms with `gpt-4o-mini` + short prompt + structured output. If real-world latency exceeds ~500 ms, Spec D will introduce speculative execution (start `chat` in parallel, cancel if classifier disagrees). Not a concern for v1.
- **Repo-search tool scope.** First cut is a simple `git grep` wrapper over the repo root, limited to text files under 1 MB. Sufficient for `code` intent demo purposes. Richer code indexing is a separate consideration.

### Explicitly deferred

- TTFT metric emission and dashboards → Spec D.
- Red-team / LLM-as-judge / regression harness → Spec E.
- Additional bypass endpoints (`/summarize`, `/code`, `/plan`).
- Per-request `intent_override` payload field.
- Retry/backoff policies.
- Human-in-the-loop interrupts (plan-approval mode).

---

*End of spec. Implementation plan to follow in `docs/superpowers/specs/2026-04-14/supervisor-orchestration-plan.md`.*
