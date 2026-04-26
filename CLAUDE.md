# [CLAUDE.md](http://CLAUDE.md)

Short briefing for Claude Code working in this repo. Keep this file tight — it loads into every conversation.

## Project

Deep Agents research assistant demo: FastAPI + `deepagents`/LangGraph backend (`apps/api/`) streams SSE events to a Next.js 14 dashboard (`apps/web/`). Single endpoint `POST /research` proxied through `/api/research` on the web side.

## Working style

- **Think before coding.** State assumptions. When a request has multiple readings, surface them — don't silently pick. If something's unclear, stop and ask.
- **Simplicity first.** Minimum code that solves the problem. No speculative abstractions, no "flexibility" that wasn't asked for, no error handling for impossible states.
- **Surgical changes.** Every diff line traces to the request. Don't "improve" adjacent code, reformat untouched files, or refactor what isn't broken. Match existing style even if you'd personally do it differently.
- **Goal-driven execution.** Turn vague asks into verifiable criteria before you start ("fix the bug" → "write a failing test, then make it pass"). For multi-step work, plan briefly and verify each step.

## Where to look


| Need                                      | Read                            |
| ----------------------------------------- | ------------------------------- |
| Structure, layers, request flow           | `.claude/rules/architecture.md` |
| Code style, async, SSE, React conventions | `.claude/rules/guidelines.md`   |
| Tool commands, commits, branches          | `CONTRIBUTING.md`               |
| Design background, prompt versioning      | `docs/`                         |


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

## Project rules

- **Follow the rules files.** If architecture.md or guidelines.md conflicts with habit, rules win.
- **Prompts are versioned.** Never edit an existing `prompts/<name>/vN.md` — add a new version and update `active.yaml`.
- **SSE events are a contract.** New event types need matching changes in `apps/api/app/streaming/events.py`, `apps/web/lib/types.ts` (`SSEEventMap`), and the `useResearchStream` reducer.
- **Tests mock LLMs and Tavily.** Never hit real APIs in `pytest` or `vitest`.
- **Don't block the event loop.** Async everywhere in the API; use `httpx.AsyncClient`, not `requests`.

## Commit behavior

- **Format:** Conventional Commits with scopes `api` / `web` / `docs` / `ci`. Example: `feat(api): add SSE event for token compression`
- **No trailers.** Omit `Co-Authored-By`, sign-offs, or other metadata. Let `git log --format=fuller` record authorship.
- **Ask before pushing.** Confirm before `git push`, creating/updating PRs, or force operations (`--force`, `--force-with-lease`, `reset --hard`, etc.).


<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
