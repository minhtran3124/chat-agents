# Deep Agents Research Assistant

A FastAPI + Next.js 14 demo showcasing multi-agent orchestration with [LangChain Deep Agents](https://github.com/langchain-ai/deepagents) and [LangGraph](https://github.com/langchain-ai/langgraph).

## How it works

Two endpoints sit behind a single chat interface:

| Endpoint | Behaviour |
| :--- | :--- |
| `POST /chat` | Classifier routes the question to one of 6 specialists |
| `POST /research` | Bypasses classifier; always runs the full deep-research pipeline |

Both stream progress over SSE to a live Next.js dashboard. The deep-research pipeline uses the 5 built-in Deep Agents capabilities: planning, virtual filesystem, subagent spawning, context compression, and cross-conversation memory.

## Stack

| Layer | Technology |
| :--- | :--- |
| Backend | Python 3.11+, FastAPI, LangGraph, LangChain Deep Agents |
| Frontend | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS |
| LLM | OpenAI gpt-4o / gpt-4o-mini (default) — switchable to Anthropic or Google |
| Search | Tavily API |
| State | SQLite (LangGraph checkpointer) |

## Quickstart

**Backend**
```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env       # fill OPENAI_API_KEY and TAVILY_API_KEY
uvicorn app.main:app --reload --port 8000
```

**Frontend** (separate terminal)
```bash
cd apps/web
npm install
cp .env.example .env.local  # set API_URL=http://localhost:8000
npm run dev                  # http://localhost:3000/research
```

## Docs

- [Backend reference](./apps/api/README.md) — endpoints, agents, SSE events, model config
- [Frontend reference](./apps/web/README.md) — SSE client, components, testing
- [Design spec](./docs/specs/2026-04-13-deep-agents-research-assistant-design.md)
- [Contributing guide](./CONTRIBUTING.md)
