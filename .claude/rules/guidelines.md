# Engineering Guidelines

Tool commands (ruff, mypy, eslint, prettier, vitest, pytest) live in `CONTRIBUTING.md`.
This file covers **how to write code** that fits the project's conventions.

---

## Quick Reference

| Concern     | Backend (`apps/api/`)                          | Frontend (`apps/web/`)                                    |
| :---------- | :--------------------------------------------- | :-------------------------------------------------------- |
| Language    | Python 3.11+                                   | TypeScript 5+ (strict)                                    |
| Framework   | FastAPI 0.115+                                 | Next.js 14.2 App Router, React 18                         |
| Formatter   | `ruff format`                                  | `prettier` + `prettier-plugin-tailwindcss`                |
| Linter      | `ruff check`                                   | `eslint` (`next lint`)                                    |
| Types       | `mypy` (`disallow_untyped_defs=true`)          | `tsc` via `next build`                                    |
| Tests       | `pytest` + `pytest-asyncio` (auto mode)        | `vitest` + `@testing-library/react`                       |
| Style       | Line 100, double quotes, 4-space indent        | Prettier defaults + Tailwind class sort                   |

---

## FastAPI Best Practices

### Structure & Layering
- All API I/O uses **Pydantic models**. Never raw dicts or loose kwargs at the boundary (RORO).
- **Routers validate + delegate.** No business logic in routers.
- **Services own** agent/LLM/prompt/tool logic. Keep side effects behind explicit service functions.
- Config only via `pydantic-settings` loaded in `config/settings.py`. Do **not** read `os.environ` elsewhere.

### Async
- Every I/O-bound function is `async def` — HTTP handlers, LLM calls, Tavily search, checkpointer reads.
- Pure/CPU work stays sync `def`.
- Do **not** block the event loop: no `requests`, no `time.sleep`, no sync file I/O in hot paths. Use `httpx.AsyncClient`, `asyncio.sleep`, `aiofiles` if needed.

### Streaming (SSE)
- SSE responses return `EventSourceResponse` from `sse-starlette`.
- Build every event through the factory functions in `app/streaming/events.py`. Keep the event shape consistent with the frontend's `SSEEventMap` type.
- **Errors mid-stream are SSE `error` events**, not raised exceptions — the HTTP status is already 200.
- Keep the event loop yielding — if chunk processing is heavy, split it into multiple yields.

### Errors & Validation
- Use FastAPI's built-in Pydantic validation for input errors.
- Throw `HTTPException(status_code=..., detail=...)` in routers for client-facing failures. Provide a structured `detail` dict, not a raw string, so the frontend can branch on it.
- **Fail fast with guard clauses.** Check preconditions at the top of a function and return early; avoid deep `else` nesting.
- Never swallow exceptions in services — log with context, then re-raise or translate in the router.

### Dependency Injection
- Use FastAPI `Depends()` for shared resources: settings, stores, checkpointer, prompt registry, LLM factory.
- Wire singletons (LLM clients, prompt registry, checkpointer) in `lifespan` at startup — **not at import time**.

### Testing
- Mock LLM providers and Tavily. **Never hit real APIs** in unit or integration tests.
- Markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`.
- Shared fixtures in `tests/conftest.py`. Parametrize edge cases with `@pytest.mark.parametrize`.
- `asyncio_mode = "auto"` is configured — any `async def test_…` works without `@pytest.mark.asyncio`.

### Ruff & mypy (configured in `pyproject.toml`)
- Line length 100. Double quotes. 4-space indent.
- Rule sets enabled: `E W F I B UP SIM ASYNC RUF`. Fix, don't silence. No `# noqa` without an inline reason.
- `disallow_untyped_defs=true` — every `def` signature needs types.
- `Any` is a code smell. Justify every use (usually a 3rd-party gap).

---

## Python Code Style

- **Descriptive names with auxiliary verbs**: `is_ready`, `has_tokens`, `can_stream`.
- Files and directories: lowercase with underscores (`agent_factory.py`).
- Prefer **functions over classes**. Classes only when state, inheritance, or Pydantic modeling is required.
- Logger: `logging.getLogger(__name__)`. Prefix messages with module context: `logger.info("[agent_factory] building researcher subagent")`.
- **Never log secrets**: API keys, tokens, or prompts containing PII.
- Default to **no comments**. Only add one when the *why* is non-obvious (a workaround, a subtle invariant). Well-named code explains the *what*.

---

## React Best Practices

- **Function components only.** Hooks for state, effects, memoization.
- One primary component per file. Co-locate component-only hooks and types in the same file.
- Keep **render pure** — no side effects in the render path. Data fetching goes in `useEffect` or a custom hook (e.g. `useResearchStream`).
- Derive UI state from props + `useState`. Avoid redundant state that can be computed.
- `key` on every list item — **stable identifier**, never array index when items can reorder, filter, or be inserted.
- Memoize only after profiling shows a real cost (`useMemo`, `useCallback`, `React.memo`). Premature memoization hurts readability and often doesn't help.
- **Explicit Props types** at the top of the file. No implicit `any`.
- Prefer composition over large prop APIs. If a component has 10+ props, split it.

---

## Next.js (App Router) Best Practices

- **App Router only.** The project uses `app/`; no `pages/` routes.
- **Server Components by default.** Add `"use client"` only when the file needs state, effects, refs, browser APIs, or event handlers.
- Keep client components as **leaves**. Pass fetched data in from server components; don't lift `"use client"` to the root.
- API routes under `app/api/*/route.ts` are used to **proxy to the Python backend**. Heavy business logic stays in the Python API — the Next server is not the source of truth.
- **Streaming from the client**: use the `lib/useResearchStream.ts` hook pattern (streaming `fetch` → `lib/sseParser` → typed events). Don't use `EventSource` (it can't send a POST body).
- Provide `loading.tsx` and `error.tsx` per route segment for UX states.
- **Secrets**: server-only vars have no `NEXT_PUBLIC_` prefix. Client-accessible env vars must not contain secrets (Anthropic/OpenAI keys, Tavily keys).
- Use `next/image` for images and `next/link` for internal navigation.

---

## TypeScript Conventions

- `strict: true` in `tsconfig.json` — no opt-out per file.
- Explicit types on **exported function signatures**. Inside function bodies, let the compiler infer.
- Avoid `any`. Use `unknown` at boundaries, narrow with type guards.
- **Discriminated unions** for SSE events and API responses — see `lib/types.ts` → `SSEEventMap` for the canonical pattern.
- `type` for unions, aliases, and primitive-like shapes. `interface` for object shapes intended to be extended.
- Prefer path aliases (e.g. `@/lib/…`) over deep relative imports (`../../../lib/…`) when configured.

---

## Styling — Tailwind CSS (No Component Library)

> The project does **not** use shadcn/ui, Radix, Material-UI, or Chakra. Do not add `import { Button } from "@/components/ui/button"` — it doesn't exist. Build with Tailwind utilities.

- **Tailwind 3.4** with `@tailwindcss/typography` (the `prose` class renders markdown from `react-markdown`).
- **Class ordering is enforced by `prettier-plugin-tailwindcss`**. Don't hand-sort. Run `prettier --write` and stop second-guessing.
- **Extract a component before extracting a `className` variable.** If the same class string repeats 3+ times, make a component.
- Use **semantic HTML** first (`<button>`, `<nav>`, `<article>`, `<main>`), Tailwind for appearance.
- **Mobile-first responsive**: unprefixed classes are mobile; use `sm:` / `md:` / `lg:` / `xl:` for breakpoints. Never write desktop-first with `max-md:` overrides unless there's a concrete reason.
- Use `tailwind.config.ts` to extend the theme (colors, fonts, spacing) — don't inline arbitrary `[value]` classes more than once. If it repeats, lift it to the theme.
- Keep `tailwind.config.ts`'s `content` globs accurate so unused classes are purged.

If a component library is introduced later, add a section here covering import patterns, theming, and interaction with Tailwind.

---

## SSE / API Contract

The frontend consumes the backend on `/research` via SSE. Two files are the contract — **keep them in sync**:

- Server event factories: `apps/api/app/streaming/events.py`
- Client type map: `apps/web/lib/types.ts` → `SSEEventMap`

When you add a new event type:

1. Add the factory function in `events.py` and emit it from `chunk_mapper.py`.
2. Add the event shape to `SSEEventMap`.
3. Handle it in `useResearchStream.ts` (update state shape).
4. Update both a backend unit test and a frontend hook test.

---

## Testing

### Backend (`pytest`)
- Every public function with branches gets a **unit test**.
- Service-level wiring (e.g. `build_research_agent`) gets an **integration test** with mocks for LLM + Tavily.
- One **end-to-end smoke** per user-facing feature (the full SSE flow for `/research`).
- Run from `apps/api/`:

  ```bash
  pytest                              # full suite
  pytest -m unit                      # by marker
  pytest tests/unit/test_file.py -v   # a specific file
  ```

### Frontend (`vitest` + Testing Library)
- Every **custom hook** and every **component with conditional UI** gets a test.
- Query priority: `getByRole` > `getByLabelText` > `getByText` > `getByTestId`.
- Mock `sseParser` when testing the hook; mock the hook when testing the component.
- Run from `apps/web/`: `npm test` (watch: `npm run test:watch`).

---

## Pre-Commit Checklist

- [ ] Type hints / TypeScript types on all public signatures
- [ ] `async` on all I/O (backend)
- [ ] Pydantic models at API boundaries (backend)
- [ ] Server Component by default (frontend); `"use client"` only when needed
- [ ] Tailwind classes formatted by `prettier-plugin-tailwindcss`
- [ ] SSE event types updated on **both sides** when the contract changes
- [ ] No secrets in `NEXT_PUBLIC_` env vars
- [ ] Tests added / updated for behavioral changes
- [ ] Backend: `ruff check . && ruff format --check . && mypy app/` clean
- [ ] Frontend: `npm run lint && npm run format:check` clean, `next build` succeeds
- [ ] Commit message follows Conventional Commits — `feat(api):`, `fix(web):`, `docs:`, `chore:`, `refactor:`, `test:`, `style:`
