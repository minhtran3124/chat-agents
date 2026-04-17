# CLAUDE.md

Short briefing for Claude Code working in this repo. Keep this file tight — it loads into every conversation.

---

## Project

Deep Agents research assistant demo: FastAPI + `deepagents`/LangGraph backend (`apps/api/`) streams SSE events to a Next.js 14 dashboard (`apps/web/`).

Two endpoints: `POST /chat` (classifier → 6 specialists) and `POST /research` (direct deep-research), both proxied through `/api/research` on the web side.

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

Env: `apps/api/.env` needs `OPENAI_API_KEY` (default) or provider-matching key + `TAVILY_API_KEY`. `apps/web/.env.local` needs `API_URL`.

---

## Behavioral Guidelines

### 1. Think Before Coding

**Don't assume. Surface tradeoffs. Ask when unclear.**

Before implementing anything in this repo:
- State assumptions explicitly — especially around the SSE contract, LangGraph graph wiring, or provider config.
- If multiple approaches exist (e.g., adding a new event type vs. reusing an existing one), name the options; don't pick silently.
- If a simpler path exists, say so.
- If the request touches the SSE contract, the supervisor graph, or prompt versioning — stop and confirm scope before writing a single line.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No new abstractions for single-use code — three similar lines beats a premature helper.
- No extra error handling for scenarios that can't happen inside this system.
- If the diff is 200 lines and 50 would do, rewrite it.

Ask: *"Would a senior engineer say this is overcomplicated?"* If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

- Don't improve adjacent code, comments, or formatting while fixing something unrelated.
- Match existing style — double-quoted Python strings, 4-space indent, Tailwind class order via Prettier.
- If you notice dead code you didn't create, mention it — don't delete it.
- Remove imports/variables/functions that **your** changes made unused. Leave pre-existing ones alone unless asked.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

For tasks in this repo, translate requests into verifiable goals:

| Request | Success criterion |
| :------ | :---------------- |
| "Add a new SSE event" | Backend emits it; `SSEEventMap` updated; reducer handles it; test exists on both sides |
| "Fix streaming bug" | Write a test that reproduces it, then make it pass |
| "Add an agent" | `specs.py` entry + builder + tool wiring + unit test; graph builds without error |

For multi-step tasks, state a brief plan before touching code:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

---

## Hard Rules

- **SSE events are a contract.** New event types need matching changes in `apps/api/app/streaming/events.py`, `apps/web/lib/types.ts` (`SSEEventMap`), and the `useResearchStream` reducer.
- **Prompts are versioned.** Never edit an existing `prompts/<name>/vN.md` — add a new version and update `active.yaml`.
- **Tests mock LLMs and Tavily.** Never hit real APIs in `pytest` or `vitest`.
- **Don't block the event loop.** Async everywhere in the API; use `httpx.AsyncClient`, not `requests`.
- **Conventional Commits** with scopes `api` / `web` / `docs` / `ci`. Ask before pushing, creating PRs, or force operations.
