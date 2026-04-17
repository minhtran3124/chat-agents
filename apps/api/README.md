# API — Deep Agents Research Backend

FastAPI service with two SSE endpoints backed by LangGraph + LangChain Deep Agents.

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in OPENAI_API_KEY and TAVILY_API_KEY
uvicorn app.main:app --reload --port 8000
```

## Endpoints

| Method | Path | Behaviour |
| :----- | :--- | :-------- |
| `POST` | `/research` | Bypasses classifier; always runs the deep-research pipeline |
| `POST` | `/chat` | Runs classifier first, then routes to the appropriate specialist |
| `GET`  | `/health` | Liveness check |

Both return `text/event-stream`. Request body fields:

```json
{
  "question": "string (required)",
  "thread_id": "string (optional — continues an existing conversation)",
  "prompt_versions": { "main": "v2" }
}
```

## Architecture

### Directory Structure

```
app/
├── agents/
│   ├── specs.py              # 6 AgentSpecs registered at startup
│   ├── classifier.py         # Structured-output intent classifier
│   ├── supervisor_graph.py   # build_supervisor_graph() + build_deep_research_only_graph()
│   └── builders/
│       ├── deep_research.py  # deepagents create_deep_agent() — planner + researcher + critic
│       └── react.py          # create_react_agent() — all other specialists
├── routers/
│   ├── chat.py               # POST /chat handler
│   ├── research.py           # POST /research handler
│   └── _runner.py            # Shared async graph runner + SSE emitter
├── tools/
│   ├── registry.py           # Decorator-based tool registration
│   ├── web_search.py         # Tavily search
│   ├── fetch_url.py          # httpx URL fetcher
│   └── repo_search.py        # git grep wrapper
├── services/
│   └── prompt_registry.py    # File-backed versioned prompts (prompts/)
├── models/
│   └── registry.py           # ModelRegistry — builds LLM clients from models.yaml
├── streaming/
│   ├── events.py             # SSE event factory functions
│   └── chunk_mapper.py       # LangGraph stream → SSE events
├── stores/
│   └── memory_store.py       # SQLite checkpointer + in-memory store
├── schemas/                  # Pydantic request/response models
└── config/
    └── settings.py           # pydantic-settings — loaded from .env
```

### Agent Routing

```
POST /chat
  → Classifier (LLM structured output — intent + confidence)
       ├── deep-research → Deep Agents pipeline (planner → researcher × N → critic)
       ├── research      → ReAct (web_search, fetch_url)
       ├── code          → ReAct (repo_search, fetch_url)
       ├── planner       → ReAct (no search tools)
       ├── summarize     → ReAct (no search tools)
       └── chat          → ReAct (no tools)

POST /research
  → deep-research directly (no classification step)
```

Fallback: confidence < 0.55 → `chat`. Stickiness: current intent retained when confidence ≥ 0.40 (prevents thrashing on follow-up questions).

### Agent Specifications (`specs.py`)

| Name | Model role | Tools | Subagents |
| :--- | :--------- | :---- | :-------- |
| `chat` | fast | — | — |
| `research` | main | web_search, fetch_url | — |
| `deep-research` | main | web_search | researcher, critic |
| `researcher` *(subagent)* | fast | web_search | — |
| `critic` *(subagent)* | fast | — | — |
| `summarize` | fast | — | — |
| `code` | main | repo_search, fetch_url | — |
| `planner` | fast | — | — |

### SSE Events

| Event | Key payload fields | Description |
| :---- | :----------------- | :---------- |
| `stream_start` | `thread_id`, `started_at` | Stream opened |
| `intent_classified` | `intent`, `confidence`, `fallback_used` | Classifier decision (chat only) |
| `todo_updated` | `items[]` — `{content, status}` | Plan step added or updated |
| `subagent_started` | `id`, `name`, `task` | Researcher spawned for a todo |
| `subagent_completed` | `id`, `summary` | Researcher finished; summary attached |
| `file_saved` | `path`, `size_tokens`, `preview` | Virtual FS write |
| `compression_triggered` | `original_tokens`, `compressed_tokens`, `synthetic` | Context compression detected |
| `text_delta` | `content` | Incremental report chunk |
| `memory_updated` | `namespace`, `key` | Cross-session memory write |
| `error` | `message`, `recoverable` | Mid-stream error (HTTP 200 body) |
| `stream_end` | `final_report`, `usage`, `versions_used` | Stream closed |

### Model Configuration (`models.yaml`)

Three named roles map to LLM instances:

```yaml
classifier:   gpt-4o-mini   # structured-output routing (no streaming)
fast:         gpt-4o-mini   # lightweight agents (subagents, summarizer)
main:         gpt-4o        # primary research agent
```

Override any role at runtime:

```bash
MAIN_PROVIDER=anthropic   MAIN_MODEL=claude-sonnet-4-6
FAST_PROVIDER=anthropic   FAST_MODEL=claude-haiku-4-5-20251001
```

Supported providers: `openai` (default), `anthropic`, `google`.

### Prompt Versioning (`prompts/`)

```
prompts/
├── active.yaml        # name → active version   e.g. main: v1
├── main/
│   └── v1.md
├── researcher/
│   └── v1.md
├── critic/v1.md
├── classifier/v1.md
├── chat/v1.md
├── research/v1.md
├── summarize/v1.md
├── code/v1.md
└── planner/v1.md
```

Rules:
- **Never edit** an existing `vN.md`. Add `v2.md` and update `active.yaml`.
- Hot-reload without restart: send `SIGHUP` to the uvicorn process.
- Per-request override: include `"prompt_versions": { "main": "v2" }` in the request body.

### Persistence

- **Checkpointer**: SQLite at `data/checkpoints.sqlite` (LangGraph thread state).
- **In-memory store**: cross-session key-value snapshots (compression scratch pad).
- Both are initialised in the FastAPI `lifespan` context and injected via `Depends()`.

## Test

```bash
pytest                              # full suite
pytest -m unit                      # unit tests only
pytest tests/unit/test_file.py -v   # single file
pytest --cov=app --cov-report=term-missing
```

Markers: `unit`, `integration`, `e2e`. Never hit real LLM or Tavily APIs in tests — all external calls are mocked.

## Lint / Format / Typecheck

```bash
ruff check .             # lint (rules: E W F I B UP SIM ASYNC RUF)
ruff format .            # format (line length 100, double quotes)
ruff format --check .    # CI check
mypy app/                # strict typing (disallow_untyped_defs=true)
```

## Environment Variables

| Variable | Required | Default | Description |
| :------- | :------- | :------ | :---------- |
| `OPENAI_API_KEY` | Yes (default provider) | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | If using Anthropic | — | Anthropic API key |
| `GOOGLE_API_KEY` | If using Google | — | Google API key |
| `TAVILY_API_KEY` | Yes | — | Tavily web search key |
| `MAIN_PROVIDER` | No | `openai` | LLM provider for main role |
| `MAIN_MODEL` | No | `gpt-4o` | Model for main role |
| `FAST_PROVIDER` | No | `openai` | LLM provider for fast role |
| `FAST_MODEL` | No | `gpt-4o-mini` | Model for fast role |
| `CLASSIFIER_PROVIDER` | No | `openai` | LLM provider for classifier |
| `CLASSIFIER_MODEL` | No | `gpt-4o-mini` | Model for classifier |
