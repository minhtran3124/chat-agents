# Architecture Reference

Authoritative architecture reference. Consult before implementing, debugging, or reviewing.

---

## Project Overview

A **Deep Agents research assistant**: a FastAPI backend orchestrates a LangChain Deep Agents pipeline (planner + researcher + critic subagents) and streams progress to a Next.js 14 frontend over Server-Sent Events.

Two-app monorepo with **no root workspace manager** (no pnpm/bun). Each app is installed independently:

- `apps/api/` — Python 3.11+ FastAPI backend
- `apps/web/` — Next.js 14 (App Router) + React 18 + TypeScript frontend

---

## Monorepo Layout

```
chat-agents/
├── apps/
│   ├── api/                 # FastAPI backend
│   └── web/                 # Next.js frontend
├── docs/                    # Design specs, plans, research outputs
├── .claude/                 # Claude Code rules, agents, skills, hooks
├── CONTRIBUTING.md          # Style + testing + commit conventions
└── .editorconfig            # Cross-editor formatting baseline
```

---

## Backend (`apps/api/`)

### Directory Structure

```
apps/api/
├── app/
│   ├── main.py              # FastAPI factory + lifespan; registers routers + middleware
│   ├── config/
│   │   └── settings.py      # pydantic-settings: LLM provider, API keys, thresholds
│   ├── routers/
│   │   └── research.py      # POST /research → SSE stream
│   ├── schemas/             # Pydantic v2 request/response models (ResearchRequest, …)
│   ├── services/
│   │   ├── agent_factory.py   # build_research_agent() → create_deep_agent(...)
│   │   ├── llm_factory.py     # Provider-agnostic LLM selection (Anthropic/OpenAI/Google)
│   │   ├── prompt_registry.py # File-backed prompt versions with per-request overrides
│   │   └── search_tool.py     # Tavily web-search wrapper
│   ├── streaming/
│   │   ├── events.py        # SSE event factory functions
│   │   └── chunk_mapper.py  # LangGraph stream modes → SSE events
│   └── stores/
│       └── memory_store.py  # SQLite checkpointer + cross-session store
├── prompts/                 # Markdown prompt files, versioned (main/, researcher/, critic/)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── data/                    # Runtime SQLite checkpoint (gitignored)
└── pyproject.toml           # Deps, ruff, mypy, pytest config
```

### Layer Responsibilities

| Layer         | Role                                                                                 |
| :------------ | :----------------------------------------------------------------------------------- |
| `routers/`    | HTTP interface — validate with Pydantic, delegate to services, return `EventSourceResponse` |
| `services/`   | Business logic — agent building, LLM selection, prompt resolution, tool construction |
| `streaming/`  | Transform LangGraph stream output into typed SSE events consumed by the frontend    |
| `stores/`     | Persistence primitives (SQLite checkpointer, cross-session memory store)             |
| `schemas/`    | Pydantic v2 models for all API I/O (RORO pattern)                                    |
| `config/`     | `pydantic-settings` loaded from env vars                                             |

### Request Flow

```
POST /research  { question, prompt_versions? }
  → Pydantic validation (ResearchRequest)
  → services/agent_factory.build_research_agent(settings, registry)
  → create_deep_agent(tools=[tavily_search], subagents=[researcher, critic])
  → streaming/chunk_mapper: LangGraph stream → SSE events
  → sse-starlette EventSourceResponse → HTTP 200 + text/event-stream
```

SSE event types currently emitted:

`stream_start`, `todo_updated`, `file_saved`, `subagent_started`, `subagent_completed`, `compression_triggered`, `text_delta`, `memory_updated`, `stream_end`, `error`.

### Key Dependencies

| Concern             | Library                                                   |
| :------------------ | :-------------------------------------------------------- |
| Web framework       | FastAPI 0.115+ / uvicorn[standard]                        |
| Agent orchestration | `deepagents` 0.5.2+, `langgraph` 1.0+, `langchain` 1.0+   |
| LLM providers       | `langchain-anthropic`, `langchain-openai`, `langchain-google-genai` |
| State / memory      | `langgraph-checkpoint-sqlite` (file-backed SQLite)        |
| Web search tool     | `tavily-python`                                           |
| SSE                 | `sse-starlette`                                           |
| Validation          | `pydantic` 2.7+, `pydantic-settings`                      |
| Tokens              | `tiktoken`                                                |

---

## Frontend (`apps/web/`)

### Directory Structure

```
apps/web/
├── app/                     # Next.js App Router
│   ├── layout.tsx           # Root layout
│   ├── page.tsx             # Landing
│   ├── research/
│   │   ├── page.tsx         # Research dashboard
│   │   └── components/      # Dashboard panels (todos, files, subagents, transcript)
│   └── api/
│       └── research/        # Server-side proxy to FastAPI SSE endpoint
├── lib/
│   ├── types.ts             # SSEEventMap + schemas for frontend parsing
│   ├── sseParser.ts         # Parses `text/event-stream` into typed events
│   └── useResearchStream.ts # Hook: fetch + SSE → component state
├── public/                  # Static assets
├── package.json             # npm (not pnpm/bun)
├── tailwind.config.ts
└── tsconfig.json            # strict: true
```

### Key Dependencies

| Concern           | Library                                                               |
| :---------------- | :-------------------------------------------------------------------- |
| Framework         | Next.js 14.2.35 (App Router)                                          |
| UI runtime        | React 18 + TypeScript 5+ (strict)                                     |
| Styling           | Tailwind CSS 3.4 + `@tailwindcss/typography`                          |
| Markdown          | `react-markdown` + `remark-gfm`                                       |
| State             | Built-in React hooks — **no** Zustand / Redux / TanStack Query        |
| SSE client        | Native `fetch` + custom parser (`lib/sseParser.ts`)                   |
| Testing           | `vitest` + `@testing-library/react` + `jsdom`                         |
| Format / lint     | `prettier`, `prettier-plugin-tailwindcss`, ESLint (`eslint-config-next`) |

**Component libraries allowed.** The project uses Tailwind CSS as the foundation. Component libraries (shadcn/ui, Headless UI, Radix, etc.) are adopted strategically for complex interactive patterns (modals, dropdowns, date pickers, tables) where they reduce workload and improve accessibility. See `guidelines.md` → *Styling & Components* for conventions.

---

## Key Patterns

| Pattern                | Implementation                                                          |
| :--------------------- | :---------------------------------------------------------------------- |
| App factory + lifespan | FastAPI `create_app()` in `main.py`, checkpointer init on startup       |
| Provider-agnostic LLMs | `llm_factory.get_llm(model_kind)` selects by settings                   |
| Prompt version registry | File-backed registry (`prompts/`) + per-request override field `prompt_versions` |
| SSE streaming          | `EventSourceResponse` server-side; custom parser + hook on the client  |
| RORO                   | All API I/O uses Pydantic models                                        |
| Deep Agents subagents  | `researcher` (Tavily + summarize), `critic` (draft review) via `create_deep_agent` |

---

## Infrastructure

| Component     | Technology                                                              |
| :------------ | :---------------------------------------------------------------------- |
| Runtime       | Python 3.11+ on the API, Node 20+ on the web                            |
| State         | SQLite (`data/checkpoints.sqlite`) — LangGraph checkpointer only. **No** Postgres, **no** Redis. |
| AI providers  | Anthropic (default: `claude-sonnet-4-6`), OpenAI, Google Gemini (via LangChain wrappers) |
| Web search    | Tavily (free tier)                                                      |
| Transport     | HTTP + Server-Sent Events                                               |
| Deployment    | Not defined in-repo                                                     |
