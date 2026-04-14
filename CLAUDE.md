# CLAUDE.md

Short briefing for Claude Code working in this repo. Keep this file tight — it loads into every conversation.

## Project

Deep Agents research assistant demo: FastAPI + `deepagents`/LangGraph backend (`apps/api/`) streams SSE events to a Next.js 14 dashboard (`apps/web/`). Single endpoint `POST /research` proxied through `/api/research` on the web side.

## Where to look

| Need | Read |
| :--- | :--- |
| Structure, layers, request flow | `.claude/rules/architecture.md` |
| Code style, async, SSE, React conventions | `.claude/rules/guidelines.md` |
| Tool commands, commits, branches | `CONTRIBUTING.md` |
| Design background, prompt versioning | `docs/` |

## Commands

```bash
# backend
cd apps/api && uvicorn app.main:app --reload --port 8000
cd apps/api && pytest                   # all
cd apps/api && ruff check . && mypy app/

# frontend
cd apps/web && npm run dev              # :3000/research
cd apps/web && npm test
cd apps/web && npm run lint
```

Env: `apps/api/.env` needs `ANTHROPIC_API_KEY` (or `OPENAI_`/`GOOGLE_API_KEY` matching `LLM_PROVIDER`) and `TAVILY_API_KEY`. `apps/web/.env.local` needs `API_URL`.

## How to work here

- **Follow the rules files.** If architecture.md or guidelines.md conflicts with habit, rules win.
- **Prompts are versioned.** Never edit an existing `prompts/<name>/vN.md` — add a new version and update `active.yaml`.
- **SSE events are a contract.** New event types need matching changes in `apps/api/app/streaming/events.py`, `apps/web/lib/types.ts` (`SSEEventMap`), and the `useResearchStream` reducer.
- **Tests mock LLMs and Tavily.** Never hit real APIs in `pytest` or `vitest`.
- **Don't block the event loop.** Async everywhere in the API; use `httpx.AsyncClient`, not `requests`.
- **Conventional Commits** with scopes `api` / `web` / `docs` / `ci`. Ask before pushing, creating PRs, or force operations.
