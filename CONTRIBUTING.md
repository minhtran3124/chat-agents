# Contributing

## Code Style

### Python (`apps/api/`)
- Formatter & linter: **Ruff** (`ruff format` + `ruff check`)
- Type checker: **mypy** (`mypy app/`)
- Type hints required on every function (params + return)
- Async/await for all I/O
- Pydantic models for all API I/O — no raw dicts

### TypeScript (`apps/web/`)
- Formatter: **Prettier** (`npm run format`)
- Linter: **ESLint** via `next lint` (`npm run lint`)
- Strict mode enabled (`tsconfig.json`)
- Functional components only; hooks for state

### Cross-cutting
- Config in `.editorconfig` (indent, EOL, charset)
- Line endings normalized to LF via `.gitattributes`
- Never commit `.env*` files

## Testing

| Where | Tool | How |
|---|---|---|
| Backend | pytest + pytest-asyncio | `cd apps/api && pytest` |
| Frontend | vitest | `cd apps/web && npm test` |

Targets:
- Unit tests for every public function with branches
- Integration tests for service-level wiring
- One end-to-end smoke per feature

## Commit Convention

Conventional Commits (https://www.conventionalcommits.org):

```
<type>(<scope>): <subject>

<body>
```

Common types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `style`.
Common scopes: `api`, `web`, `docs`, `ci`.

Examples:
- `feat(api): provider-agnostic LLM factory`
- `fix(web): SSE parser handles multi-line data correctly`
- `docs: update demo verification checklist`

## Changelog

Every PR that changes user-visible behavior updates `/CHANGELOG.md`'s
`[Unreleased]` section. Use the [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
subhead convention:

- **Added** — new features, new events, new settings, new files.
- **Changed** — existing behavior changed in a backward-incompatible or
  observable way.
- **Deprecated** — features marked for removal in a future release.
- **Removed** — features removed in this change.
- **Fixed** — bug fixes.
- **Security** — vulnerability fixes.

Pure internal refactors (no user-visible or operator-visible effect) can
skip the changelog. When in doubt, add an entry — it's cheap.

When a release is cut, rename `## [Unreleased]` to `## [x.y.z] - YYYY-MM-DD`,
and start a new empty `## [Unreleased]` section above it.

## Branch Naming

- Feature branches: `feat/<short-name>` e.g. `feat/research-dashboard`
- Bug fixes: `fix/<short-name>`
- Docs: `docs/<short-name>`

## Running Lint Locally Before Push

```bash
# backend
cd apps/api && ruff check . && ruff format --check . && mypy app/

# frontend
cd apps/web && npm run lint && npm run format -- --check
```
