# Deep Agents Research Assistant — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working FastAPI + Next.js demo that exercises all 5 LangChain Deep Agents capabilities (planning, virtual filesystem, subagents, auto-compression, cross-conversation memory) with a dashboard UI.

**Architecture:** Layered FastAPI backend (router → service → store) wraps `create_deep_agent()` with provider-agnostic LLM config. SSE streaming maps LangGraph chunks to typed events consumed by a Next.js dashboard via `fetch` + `ReadableStream`.

**Tech Stack:** Python 3.11+, FastAPI, `deepagents`, `langgraph`, `langchain`, Tavily, SQLite, sse-starlette, Next.js 14, TypeScript, Tailwind.

**Spec:** [`./2026-04-13-deep-agents-research-assistant-design.md`](./2026-04-13-deep-agents-research-assistant-design.md)

---

## File Structure (locked-in decomposition)

### Repo root

| File | Responsibility |
|---|---|
| `.editorconfig` | Cross-editor formatting baseline (indent, EOL, charset) |
| `.gitignore` | Root-level ignores (OS files, IDE files, secrets) |
| `README.md` | Project overview, monorepo layout, quickstart |
| `CONTRIBUTING.md` | Code style, commit convention, how to run tests/linters |
| `.gitattributes` | Line-ending normalization (LF) |

### Backend — `apps/api/`

| File | Responsibility |
|---|---|
| `app/main.py` | FastAPI entry, lifespan wiring, CORS, router registration |
| `app/config/settings.py` | Pydantic Settings: provider/model/keys/paths + validators |
| `app/services/llm_factory.py` | `get_llm()` / `get_fast_llm()` — provider-agnostic via `init_chat_model` |
| `app/services/search_tool.py` | Tavily wrapped as a LangChain `@tool` |
| `app/services/agent_factory.py` | `build_research_agent()` — wires subagents, store, checkpointer |
| `app/stores/memory_store.py` | Lifespan-managed `AsyncSqliteSaver` + `InMemoryStore` |
| `app/streaming/events.py` | 10 SSE event helper functions |
| `app/streaming/chunk_mapper.py` | Stateful reducer: LangGraph chunk → SSE events |
| `app/schemas/research.py` | Pydantic I/O for `/research` endpoint |
| `app/routers/research.py` | `POST /research` SSE endpoint |
| `pyproject.toml` | Pinned deps + `[tool.ruff]` (lint+format) + `[tool.mypy]` (typecheck) + `[tool.pytest]` |
| `.env.example` | Documented env vars |
| `apps/api/README.md` | Backend-specific run/test/lint instructions |
| `tests/unit/test_settings.py` | Validate provider/key pairing, default model resolution |
| `tests/unit/test_llm_factory.py` | Provider swap returns correct client class |
| `tests/unit/test_search_tool.py` | Tavily called with correct kwargs |
| `tests/unit/test_events.py` | Event helper output shape |
| `tests/unit/test_chunk_mapper.py` | Chunk diffing → correct events |
| `tests/integration/test_agent_factory.py` | Agent built with 2 subagents, store wired |
| `tests/e2e/test_research_endpoint.py` | POST /research streams expected event sequence |

### Frontend — `apps/web/`

| File | Responsibility |
|---|---|
| `app/research/page.tsx` | Dashboard route — composes form + panels |
| `app/research/components/QuestionForm.tsx` | Input + start button |
| `app/research/components/TodoList.tsx` | Renders `state.todos` |
| `app/research/components/FileList.tsx` | Renders `state.files` |
| `app/research/components/SubagentPanel.tsx` | Renders `state.subagents` + nested CompressionBadge |
| `app/research/components/CompressionBadge.tsx` | Renders compression count + `synthetic` tooltip |
| `app/research/components/ReportView.tsx` | Renders `state.report` (markdown) |
| `app/api/research/route.ts` | Proxies POST → FastAPI, streams body back |
| `lib/sseParser.ts` | Pure SSE frame parser (`consumeFrames`, `leftoverAfterFrames`) |
| `lib/useResearchStream.ts` | React hook: fetch + ReadableStream + reducer |
| `lib/types.ts` | TypeScript types matching backend SSE payloads |
| `apps/web/.prettierrc.json` | Prettier formatting config |
| `apps/web/.prettierignore` | Files prettier should skip |
| `apps/web/.eslintrc.json` | (extends `next/core-web-vitals`, scaffolded by Next.js) |
| `apps/web/README.md` | Frontend-specific run/test/lint instructions |

---

## Chunks

This plan is organized into 7 chunks. Each chunk produces a working, testable slice. Order matters — later chunks depend on earlier modules.

| # | Chunk | What's testable after |
|---|---|---|
| 0 | Repo & tooling bootstrap | `git status` clean; `.editorconfig`/`.gitignore` honored; READMEs scaffolded |
| 1 | Backend bootstrap + Settings + LLM Factory + linter | Provider swap works; key validation works; `ruff check` passes |
| 2 | Search Tool + Memory Store + Lifespan | App starts, SQLite checkpointer initializes |
| 3 | Agent Factory | `build_research_agent()` returns wired agent, mocked invoke runs |
| 4 | SSE Events + ChunkMapper + Router | E2E POST `/research` streams the expected event sequence |
| 5 | Frontend foundation (Next.js + hook + parser + proxy + prettier) | Hook receives + reduces events; `npm run lint`/`format` clean |
| 6 | Dashboard components + E2E demo verification + READMEs filled out | All 5 capabilities visible on dashboard; all READMEs complete |

---

## Chunk 0: Repo & Tooling Bootstrap

**Goal of chunk:** Repo initialized with cross-language tooling, root-level configs, and skeleton READMEs.

### Task 0.1: Initialize git + root configs

**Files:**
- Create: `.gitignore` (root)
- Create: `.gitattributes`
- Create: `.editorconfig`

- [ ] **Step 0.1.1: Initialize git** (idempotent — safe to re-run):

```bash
cd /Users/minhtran/Documents/minhtran3124/developer/chat-agents && \
  { [ -d .git ] || git init; } && git branch -M main
```

Expected: `Initialized empty Git repository in .git/` on first run, or no output if `.git/` already exists.

- [ ] **Step 0.1.2: Create root `.gitignore`:**

```gitignore
# OS
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/*
!.vscode/extensions.json
!.vscode/settings.example.json
*.swp
*.swo

# Secrets
.env
.env.local
.env.*.local
*.pem

# Logs
*.log
npm-debug.log*
yarn-debug.log*
pnpm-debug.log*

# Build artefacts
node_modules/
.next/
out/
dist/
build/

# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Local data
data/
*.sqlite
*.sqlite-journal
```

- [ ] **Step 0.1.3: Create `.gitattributes`** (force LF on text files cross-platform):

```gitattributes
* text=auto eol=lf
*.png binary
*.jpg binary
*.ico binary
*.sqlite binary
```

- [ ] **Step 0.1.4: Create `.editorconfig`** (cross-editor formatting baseline):

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 2

[*.py]
indent_size = 4
max_line_length = 100

[*.{md,markdown}]
trim_trailing_whitespace = false  # markdown uses trailing spaces for line breaks

[Makefile]
indent_style = tab
```

- [ ] **Step 0.1.5: Commit:**

```bash
git add .gitignore .gitattributes .editorconfig
git commit -m "chore: initialize repo with cross-language tooling baseline"
```

---

### Task 0.2: Root README + CONTRIBUTING skeleton

**Files:**
- Create: `README.md`
- Create: `CONTRIBUTING.md`

- [ ] **Step 0.2.1: Create root `README.md`** (filled out further in Chunk 6):

````markdown
# Deep Agents Research Assistant

Demo project showcasing the **5 built-in capabilities** of [LangChain Deep Agents](https://github.com/langchain-ai/deepagents):
1. Planning (`write_todos`)
2. Virtual filesystem (context offloading)
3. Subagent spawning
4. Automatic context compression
5. Cross-conversation memory

Each capability is **observable on a live dashboard** rather than buried in logs.

## Repository Layout

```
chat-agents/
├── apps/
│   ├── api/        # FastAPI backend (Python 3.11+, Deep Agents, LangGraph)
│   └── web/        # Next.js 14 frontend (TypeScript, Tailwind)
├── docs/           # Specs, plans, notes
├── .editorconfig   # Cross-editor formatting baseline
└── CONTRIBUTING.md # Code style + commit conventions
```

## Quickstart

### Prerequisites
- Python 3.11+
- Node.js 20+
- Anthropic API key (`sk-ant-...`)
- Tavily API key (free tier at https://tavily.com)

### 1. Backend
```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env       # fill in keys
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (separate terminal)
```bash
cd apps/web
npm install
cp .env.example .env.local # fill in API_URL
npm run dev
```

Open http://localhost:3000/research.

## Documentation

- [Design spec](./docs/2026-04-13-deep-agents-research-assistant-design.md)
- [Implementation plan](./docs/2026-04-13-deep-agents-research-assistant-plan.md)
- [Article notes (Deep Agents)](./docs/2026-04-13-langchain-deep-agents-notes.md)
- [Contributing guide](./CONTRIBUTING.md)
````

- [ ] **Step 0.2.2: Create `CONTRIBUTING.md`:**

````markdown
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
````

- [ ] **Step 0.2.3: Commit:**

```bash
git add README.md CONTRIBUTING.md
git commit -m "docs: root README + CONTRIBUTING skeleton"
```

---

## Chunk 1: Backend Bootstrap + Settings + LLM Factory

**Goal of chunk:** App boots; provider swap is configurable + validated.

### Task 1.1: Initialize backend project structure

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/.env.example`
- Create: `apps/api/app/__init__.py`
- Create: `apps/api/app/config/__init__.py`
- Create: `apps/api/app/services/__init__.py`
- Create: `apps/api/app/stores/__init__.py`
- Create: `apps/api/app/streaming/__init__.py`
- Create: `apps/api/app/schemas/__init__.py`
- Create: `apps/api/app/routers/__init__.py`
- Create: `apps/api/tests/__init__.py`
- Create: `apps/api/tests/unit/__init__.py`
- Create: `apps/api/tests/integration/__init__.py`
- Create: `apps/api/tests/e2e/__init__.py`

- [ ] **Step 1.1.1: Create `apps/api/pyproject.toml`** with pinned deps + lint/format/typecheck config:

```toml
[project]
name = "deep-agents-research-api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115,<0.120",
    "uvicorn[standard]>=0.30",
    "deepagents==0.0.20",
    "langgraph>=0.2.70,<0.3",
    "langchain>=0.3.15,<0.4",
    "langchain-anthropic>=0.3,<0.4",
    "langchain-openai>=0.3,<0.4",
    "langchain-google-genai>=2.0,<3.0",
    "langgraph-checkpoint-sqlite>=2.0,<3.0",
    "tavily-python>=0.5,<1.0",
    "sse-starlette>=2.1,<3.0",
    "pydantic>=2.7,<3.0",
    "pydantic-settings>=2.4,<3.0",
    "tiktoken>=0.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "mypy>=1.11",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra -q"

# ----- Ruff: linter + formatter (replaces black / isort / flake8 / pyupgrade) -----
[tool.ruff]
line-length = 100
target-version = "py311"
extend-exclude = ["data", ".venv"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "B",   # bugbear
    "UP",  # pyupgrade
    "SIM", # simplify
    "ASYNC", # async-specific lints
    "RUF",
]
ignore = [
    "E501",  # line length handled by formatter
]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["B011", "S101"]  # allow asserts in tests

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

# ----- mypy: strict-ish typing -----
[tool.mypy]
python_version = "3.11"
strict = false                 # demo: relaxed; tighten over time
warn_unused_ignores = true
warn_redundant_casts = true
disallow_untyped_defs = true   # require type hints on def signatures
ignore_missing_imports = true  # third-party libs without stubs
exclude = ["data/", ".venv/"]
```

- [ ] **Step 1.1.2: Create `apps/api/.env.example`:**

```bash
LLM_PROVIDER=anthropic
# LLM_MODEL=claude-sonnet-4-6   # optional, defaults from provider

ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=...

TAVILY_API_KEY=tvly-...

CHECKPOINT_DB_PATH=./data/checkpoints.sqlite
VFS_OFFLOAD_THRESHOLD_TOKENS=20000
COMPRESSION_DETECTION_RATIO=0.7
CORS_ORIGINS=["http://localhost:3000"]
```

- [ ] **Step 1.1.3: Skip — root `.gitignore` from Chunk 0 already covers all Python/build/secret patterns. No `apps/api/.gitignore` needed.**

- [ ] **Step 1.1.4: Create empty `__init__.py` in every package directory listed above.**

- [ ] **Step 1.1.5: Install deps:**

```bash
cd apps/api && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
```

Expected: install completes with no errors.

- [ ] **Step 1.1.6: Smoke-import deepagents to verify pinned version exposes required API:**

```bash
cd apps/api && source .venv/bin/activate && \
  python -c "from deepagents import create_deep_agent, SubAgent; print('deepagents API ok')"
```

Expected output: `deepagents API ok`. If this fails, the pinned version is incompatible — update `pyproject.toml` and re-install before continuing.

- [ ] **Step 1.1.7: Verify ruff + mypy run cleanly on empty package:**

```bash
cd apps/api && source .venv/bin/activate && \
  ruff check . && ruff format --check . && mypy app/
```

Expected: all three commands exit 0 (no files to lint yet, but configs valid).

- [ ] **Step 1.1.8: Scaffold `apps/api/README.md`** (filled out further in Chunk 6):

````markdown
# API — Deep Agents Research Backend

FastAPI service exposing `POST /research` SSE endpoint backed by LangChain Deep Agents.

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # add ANTHROPIC_API_KEY and TAVILY_API_KEY
uvicorn app.main:app --reload --port 8000
```

## Test

```bash
pytest                          # all
pytest tests/unit -v            # unit only
pytest tests/integration -v     # integration
pytest tests/e2e -v             # e2e (mocked agent)
pytest --cov=app --cov-report=term-missing
```

## Lint / Format / Typecheck

```bash
ruff check .            # lint
ruff format .           # format (or --check for CI)
mypy app/               # typecheck
```

## Configure LLM provider

Edit `.env`:

| Var | Values |
|---|---|
| `LLM_PROVIDER` | `anthropic` (default) / `openai` / `google` |
| `LLM_MODEL` | optional — defaults per provider |

See [docs/2026-04-13-deep-agents-research-assistant-design.md](../../docs/2026-04-13-deep-agents-research-assistant-design.md) for full architecture.
````

- [ ] **Step 1.1.9: Commit:**

```bash
git add apps/api/pyproject.toml apps/api/.env.example apps/api/README.md apps/api/app apps/api/tests
git commit -m "feat(api): bootstrap project with ruff + mypy + pytest config"
```

---

### Task 1.2: Settings module (TDD)

**Files:**
- Create: `apps/api/app/config/settings.py`
- Create: `apps/api/tests/unit/test_settings.py`

- [ ] **Step 1.2.1: Write failing tests** in `apps/api/tests/unit/test_settings.py`:

```python
import pytest
from pydantic import ValidationError


def test_anthropic_provider_with_key_resolves_default_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    from app.config.settings import Settings
    s = Settings()
    assert s.LLM_PROVIDER == "anthropic"
    assert s.LLM_MODEL == "claude-sonnet-4-6"


def test_openai_provider_resolves_correct_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    from app.config.settings import Settings
    s = Settings()
    assert s.LLM_MODEL == "gpt-4o"


def test_missing_provider_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import Settings
    with pytest.raises(ValidationError, match="OPENAI_API_KEY is missing"):
        Settings()


def test_missing_tavily_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    from app.config.settings import Settings
    with pytest.raises(ValidationError):
        Settings()


def test_explicit_llm_model_is_preserved(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5")

    from app.config.settings import Settings
    s = Settings()
    assert s.LLM_MODEL == "claude-haiku-4-5"
```

- [ ] **Step 1.2.2: Run tests, confirm they fail:**

```bash
cd apps/api && python -m pytest tests/unit/test_settings.py -v
```

Expected: ImportError (settings module doesn't exist yet).

- [ ] **Step 1.2.3: Implement `apps/api/app/config/settings.py`:**

```python
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_MODEL = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "google": "gemini-1.5-pro",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LLM_PROVIDER: Literal["anthropic", "openai", "google"] = "anthropic"
    LLM_MODEL: str | None = None

    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None

    TAVILY_API_KEY: str = Field(..., description="Required for research tool")

    CHECKPOINT_DB_PATH: str = "./data/checkpoints.sqlite"
    VFS_OFFLOAD_THRESHOLD_TOKENS: int = 20_000
    COMPRESSION_DETECTION_RATIO: float = 0.7

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def _resolve_and_validate(self):
        if self.LLM_MODEL is None:
            object.__setattr__(self, "LLM_MODEL", _DEFAULT_MODEL[self.LLM_PROVIDER])

        key_map = {
            "anthropic": self.ANTHROPIC_API_KEY,
            "openai": self.OPENAI_API_KEY,
            "google": self.GOOGLE_API_KEY,
        }
        if not key_map[self.LLM_PROVIDER]:
            raise ValueError(
                f"LLM_PROVIDER={self.LLM_PROVIDER} but "
                f"{self.LLM_PROVIDER.upper()}_API_KEY is missing"
            )
        return self


settings = Settings()  # NOTE: do not import this in unit tests — they construct fresh Settings()
```

- [ ] **Step 1.2.4: Run tests, confirm they pass:**

```bash
cd apps/api && python -m pytest tests/unit/test_settings.py -v
```

Expected: 5 passed.

- [ ] **Step 1.2.5: Commit:**

```bash
git add apps/api/app/config/settings.py apps/api/tests/unit/test_settings.py
git commit -m "feat(api): provider-agnostic settings with default model resolution"
```

---

### Task 1.3: LLM Factory (TDD)

**Files:**
- Create: `apps/api/app/services/llm_factory.py`
- Create: `apps/api/tests/unit/test_llm_factory.py`

- [ ] **Step 1.3.1: Write failing tests:**

```python
from unittest.mock import patch, MagicMock


def test_get_llm_calls_init_chat_model_with_settings(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    with patch("app.services.llm_factory.init_chat_model") as mock_init:
        mock_init.return_value = MagicMock()
        from importlib import reload
        from app.services import llm_factory
        reload(llm_factory)
        llm_factory.get_llm()
        mock_init.assert_called_once_with(
            model="claude-sonnet-4-6",
            model_provider="anthropic",
        )


def test_get_fast_llm_uses_haiku_for_anthropic(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    with patch("app.services.llm_factory.init_chat_model") as mock_init:
        from importlib import reload
        from app.services import llm_factory
        reload(llm_factory)
        llm_factory.get_fast_llm()
        mock_init.assert_called_once_with(
            model="claude-haiku-4-5",
            model_provider="anthropic",
        )


def test_get_fast_llm_uses_gpt4o_mini_for_openai(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    with patch("app.services.llm_factory.init_chat_model") as mock_init:
        from importlib import reload
        from app.services import llm_factory
        reload(llm_factory)
        llm_factory.get_fast_llm()
        mock_init.assert_called_once_with(
            model="gpt-4o-mini",
            model_provider="openai",
        )
```

- [ ] **Step 1.3.2: Run tests, confirm they fail (ImportError).**

- [ ] **Step 1.3.3: Implement `apps/api/app/services/llm_factory.py`:**

```python
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.config.settings import settings

_FAST_MODEL = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "google": "gemini-1.5-flash",
}


def get_llm() -> BaseChatModel:
    return init_chat_model(
        model=settings.LLM_MODEL,
        model_provider=settings.LLM_PROVIDER,
    )


def get_fast_llm() -> BaseChatModel:
    return init_chat_model(
        model=_FAST_MODEL[settings.LLM_PROVIDER],
        model_provider=settings.LLM_PROVIDER,
    )
```

- [ ] **Step 1.3.4: Run tests, confirm they pass.**

- [ ] **Step 1.3.5: Commit:**

```bash
git add apps/api/app/services/llm_factory.py apps/api/tests/unit/test_llm_factory.py
git commit -m "feat(api): provider-agnostic LLM factory"
```

---

## Chunk 2: Search Tool + Memory Store + Lifespan

**Goal of chunk:** Tools and persistence wired; app boots clean with SQLite checkpointer.

### Task 2.1: Search Tool (TDD)

**Files:**
- Create: `apps/api/app/services/search_tool.py`
- Create: `apps/api/tests/unit/test_search_tool.py`

- [ ] **Step 2.1.1: Write failing test:**

```python
from unittest.mock import patch, MagicMock


def test_internet_search_calls_tavily_with_kwargs(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    fake_client = MagicMock()
    fake_client.search.return_value = {"results": []}
    with patch("app.services.search_tool.TavilyClient", return_value=fake_client):
        from importlib import reload
        from app.services import search_tool
        reload(search_tool)

        result = search_tool.internet_search.invoke({
            "query": "agentic AI", "max_results": 3
        })

    fake_client.search.assert_called_once_with(
        query="agentic AI",
        max_results=3,
        topic="general",
        include_raw_content=False,
    )
    assert result == {"results": []}
```

- [ ] **Step 2.1.2: Run, confirm fail.**

- [ ] **Step 2.1.3: Implement `apps/api/app/services/search_tool.py`:**

```python
from langchain_core.tools import tool
from tavily import TavilyClient

from app.config.settings import settings

_tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)


@tool
def internet_search(
    query: str,
    max_results: int = 5,
    topic: str = "general",
    include_raw_content: bool = False,
) -> dict:
    """Search the web for up-to-date information on a topic."""
    return _tavily.search(
        query=query,
        max_results=max_results,
        topic=topic,
        include_raw_content=include_raw_content,
    )
```

- [ ] **Step 2.1.4: Run, confirm pass.**

- [ ] **Step 2.1.5: Commit:**

```bash
git add apps/api/app/services/search_tool.py apps/api/tests/unit/test_search_tool.py
git commit -m "feat(api): Tavily search wrapped as LangChain tool"
```

---

### Task 2.2: Memory Store with lifespan (TDD)

**Files:**
- Create: `apps/api/app/stores/memory_store.py`
- Create: `apps/api/tests/unit/test_memory_store.py`

- [ ] **Step 2.2.1: Write failing test:**

```python
import pytest
from pathlib import Path


@pytest.mark.asyncio
async def test_lifespan_initializes_and_tears_down_checkpointer(tmp_path, monkeypatch):
    db_path = tmp_path / "test.sqlite"
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("CHECKPOINT_DB_PATH", str(db_path))

    from importlib import reload
    from app.config import settings as cfg
    reload(cfg)
    from app.stores import memory_store
    reload(memory_store)

    # Before lifespan: checkpointer not available
    with pytest.raises(RuntimeError, match="not initialized"):
        memory_store.get_checkpointer()

    # During lifespan
    async with memory_store.lifespan_stores():
        cp = memory_store.get_checkpointer()
        assert cp is not None
        assert db_path.exists() or db_path.parent.exists()

    # After lifespan: cleared
    with pytest.raises(RuntimeError, match="not initialized"):
        memory_store.get_checkpointer()


def test_get_store_returns_in_memory_store():
    from app.stores.memory_store import get_store
    from langgraph.store.memory import InMemoryStore
    assert isinstance(get_store(), InMemoryStore)
```

- [ ] **Step 2.2.2: Run, confirm fail.**

- [ ] **Step 2.2.3: Implement `apps/api/app/stores/memory_store.py`:**

```python
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.memory import InMemoryStore

from app.config.settings import settings

_store = InMemoryStore()
_checkpointer: AsyncSqliteSaver | None = None


@asynccontextmanager
async def lifespan_stores() -> AsyncIterator[None]:
    global _checkpointer
    Path(settings.CHECKPOINT_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(settings.CHECKPOINT_DB_PATH) as cp:
        _checkpointer = cp
        try:
            yield
        finally:
            _checkpointer = None


def get_store() -> InMemoryStore:
    return _store


def get_checkpointer() -> AsyncSqliteSaver:
    if _checkpointer is None:
        raise RuntimeError(
            "Checkpointer not initialized — app lifespan not active"
        )
    return _checkpointer
```

- [ ] **Step 2.2.4: Run, confirm pass.**

- [ ] **Step 2.2.5: Commit:**

```bash
git add apps/api/app/stores/memory_store.py apps/api/tests/unit/test_memory_store.py
git commit -m "feat(api): lifespan-managed SQLite checkpointer + in-memory store"
```

---

### Task 2.3: FastAPI app entry with lifespan

**Files:**
- Create: `apps/api/app/main.py`

- [ ] **Step 2.3.1: Implement `apps/api/app/main.py`:**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.stores.memory_store import lifespan_stores


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with lifespan_stores():
        yield


app = FastAPI(title="Deep Agents Research API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 2.3.2: Boot test:**

```bash
cd apps/api && cp .env.example .env && \
  echo "ANTHROPIC_API_KEY=sk-ant-fake-for-boot-test" >> .env && \
  echo "TAVILY_API_KEY=tvly-fake-for-boot-test" >> .env && \
  python -m uvicorn app.main:app --port 8000 &
sleep 2
curl -sf http://localhost:8000/health
kill %1
```

Expected: `{"status":"ok"}`. SQLite file created at `data/checkpoints.sqlite`.

- [ ] **Step 2.3.3: Commit:**

```bash
git add apps/api/app/main.py
git commit -m "feat(api): FastAPI entry with lifespan-managed checkpointer"
```

---

## Chunk 3: Agent Factory

**Goal of chunk:** `build_research_agent()` returns a fully wired Deep Agent with subagents and stores.

### Task 3.1: Agent Factory (TDD with mocks)

**Files:**
- Create: `apps/api/app/services/agent_factory.py`
- Create: `apps/api/tests/integration/test_agent_factory.py`

- [ ] **Step 3.1.1: Write failing test:**

```python
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_build_research_agent_wires_subagents_and_store(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from importlib import reload
    from app.config import settings as cfg
    reload(cfg)

    fake_agent = MagicMock()
    with patch("app.services.agent_factory.create_deep_agent", return_value=fake_agent) as mock_cda, \
         patch("app.services.agent_factory.get_llm", return_value=MagicMock()), \
         patch("app.services.agent_factory.get_fast_llm", return_value=MagicMock()):

        from app.services import agent_factory
        reload(agent_factory)

        # Need lifespan active for checkpointer
        from app.stores.memory_store import lifespan_stores
        async with lifespan_stores():
            agent = agent_factory.build_research_agent()

        kwargs = mock_cda.call_args.kwargs
        assert agent is fake_agent
        assert "tools" in kwargs
        assert kwargs["system_prompt"]
        assert len(kwargs["subagents"]) == 2
        names = {sa.name for sa in kwargs["subagents"]}
        assert names == {"researcher", "critic"}
        assert kwargs["store"] is not None
        assert kwargs["checkpointer"] is not None
```

- [ ] **Step 3.1.2: Run, confirm fail.**

- [ ] **Step 3.1.3: Implement `apps/api/app/services/agent_factory.py`:**

```python
from deepagents import create_deep_agent, SubAgent

from app.services.llm_factory import get_llm, get_fast_llm
from app.services.search_tool import internet_search
from app.stores.memory_store import get_store, get_checkpointer

RESEARCHER_PROMPT = """You are a focused researcher. For ONE topic given by the main agent:
- Run 2-4 targeted searches.
- Save raw results to virtual filesystem.
- Return a concise 150-word summary with citations (URL + quote).
Do NOT write the final report — the main agent does that."""

CRITIC_PROMPT = """You are a skeptical critic. Read the draft report from virtual FS and:
- Flag unsupported claims (no citation).
- Flag outdated info (>2 years old unless historical).
- Flag contradictions between sources.
Return a bulleted list of issues. Do NOT rewrite."""

MAIN_PROMPT = """You are an expert research assistant. Given a research question:

1. Use `write_todos` to break the question into 3-5 sub-topics.
2. Read user preferences from the store (namespace="preferences").
3. For each sub-topic, spawn the `researcher` subagent with a specific focus.
4. Synthesize findings into a draft report saved to virtual FS as `draft.md`.
5. Spawn the `critic` subagent to review the draft.
6. Revise based on critic feedback, then output the final markdown report.
7. After answering, update the store:
     - Append this topic to namespace="topics".
     - If the user expressed a preference (tone, depth, citation style),
       update namespace="preferences".

Always cite sources inline as [1], [2], … with a References section at the end."""


def build_research_agent():
    main_llm = get_llm()
    fast_llm = get_fast_llm()

    subagents = [
        SubAgent(
            name="researcher",
            description=(
                "Deep-dive a single sub-topic: run searches, save raw "
                "results, return 150-word summary with citations."
            ),
            prompt=RESEARCHER_PROMPT,
            tools=[internet_search],
            model=fast_llm,
        ),
        SubAgent(
            name="critic",
            description=(
                "Review the draft report on virtual FS and list issues "
                "(unsupported claims, outdated info, contradictions)."
            ),
            prompt=CRITIC_PROMPT,
            tools=[],
            model=fast_llm,
        ),
    ]

    return create_deep_agent(
        model=main_llm,
        tools=[internet_search],
        subagents=subagents,
        system_prompt=MAIN_PROMPT,
        store=get_store(),
        checkpointer=get_checkpointer(),
    )
```

- [ ] **Step 3.1.4: Run, confirm pass.**

- [ ] **Step 3.1.5: Commit:**

```bash
git add apps/api/app/services/agent_factory.py apps/api/tests/integration/test_agent_factory.py
git commit -m "feat(api): research agent factory with researcher + critic subagents"
```

---

## Chunk 4: SSE Events + ChunkMapper + Router

**Goal of chunk:** End-to-end POST `/research` streams the expected SSE event sequence.

### Task 4.1: SSE Event helpers (TDD)

**Files:**
- Create: `apps/api/app/streaming/events.py`
- Create: `apps/api/tests/unit/test_events.py`

- [ ] **Step 4.1.1: Write failing test:**

```python
import json


def test_stream_start_includes_thread_id_and_iso_timestamp():
    from app.streaming.events import stream_start
    ev = stream_start("default-user")
    assert ev["event"] == "stream_start"
    payload = json.loads(ev["data"])
    assert payload["thread_id"] == "default-user"
    assert "T" in payload["started_at"]


def test_file_saved_truncates_preview():
    from app.streaming.events import file_saved
    ev = file_saved("vfs://foo.md", 1234, "x" * 1000)
    payload = json.loads(ev["data"])
    assert len(payload["preview"]) == 500
    assert payload["size_tokens"] == 1234


def test_text_delta_passes_content():
    from app.streaming.events import text_delta
    ev = text_delta("hello")
    assert ev["event"] == "text_delta"
    assert json.loads(ev["data"])["content"] == "hello"


def test_error_default_recoverable_false():
    from app.streaming.events import error
    ev = error("boom")
    assert json.loads(ev["data"])["recoverable"] is False


def test_stream_end_carries_final_report_and_usage():
    from app.streaming.events import stream_end
    ev = stream_end("# report", {"input_tokens": 100})
    p = json.loads(ev["data"])
    assert p["final_report"] == "# report"
    assert p["usage"] == {"input_tokens": 100}


def test_compression_triggered_default_not_synthetic():
    from app.streaming.events import compression_triggered
    ev = compression_triggered(10000, 5000)
    p = json.loads(ev["data"])
    assert p["original_tokens"] == 10000
    assert p["compressed_tokens"] == 5000
    assert p["synthetic"] is False


def test_compression_triggered_synthetic_flag_passes_through():
    from app.streaming.events import compression_triggered
    ev = compression_triggered(40000, 20000, synthetic=True)
    p = json.loads(ev["data"])
    assert p["synthetic"] is True
```

- [ ] **Step 4.1.2: Run, confirm fail.**

- [ ] **Step 4.1.3: Implement `apps/api/app/streaming/events.py`:**

```python
import json
from datetime import datetime, timezone
from typing import Any


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, default=str)}


def stream_start(thread_id: str) -> dict:
    return _sse("stream_start", {
        "thread_id": thread_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })


def todo_updated(items: list[dict]) -> dict:
    return _sse("todo_updated", {"items": items})


def file_saved(path: str, size_tokens: int, preview: str) -> dict:
    return _sse("file_saved", {
        "path": path, "size_tokens": size_tokens, "preview": preview[:500],
    })


def subagent_started(run_id: str, name: str, task: str) -> dict:
    return _sse("subagent_started", {"id": run_id, "name": name, "task": task})


def subagent_completed(run_id: str, summary: str) -> dict:
    return _sse("subagent_completed", {"id": run_id, "summary": summary})


def compression_triggered(
    original_tokens: int,
    compressed_tokens: int,
    synthetic: bool = False,
) -> dict:
    return _sse("compression_triggered", {
        "original_tokens": original_tokens,
        "compressed_tokens": compressed_tokens,
        "synthetic": synthetic,
    })


def text_delta(content: str) -> dict:
    return _sse("text_delta", {"content": content})


def memory_updated(namespace: str, key: str) -> dict:
    return _sse("memory_updated", {"namespace": namespace, "key": key})


def error(message: str, recoverable: bool = False) -> dict:
    return _sse("error", {"message": message, "recoverable": recoverable})


def stream_end(final_report: str, usage: dict[str, Any]) -> dict:
    return _sse("stream_end", {"final_report": final_report, "usage": usage})
```

- [ ] **Step 4.1.4: Run, confirm pass.**

- [ ] **Step 4.1.5: Commit:**

```bash
git add apps/api/app/streaming/events.py apps/api/tests/unit/test_events.py
git commit -m "feat(api): SSE event helpers (10 event types)"
```

---

### Task 4.2: ChunkMapper (TDD)

**Files:**
- Create: `apps/api/app/streaming/chunk_mapper.py`
- Create: `apps/api/tests/unit/test_chunk_mapper.py`

- [ ] **Step 4.2.1: Write failing tests:**

```python
import json
import pytest


@pytest.mark.asyncio
async def test_todos_change_emits_todo_updated():
    from app.streaming.chunk_mapper import ChunkMapper
    mapper = ChunkMapper()
    chunk = {"main": {"todos": [{"text": "Step 1", "status": "pending"}]}}
    events = [ev async for ev in mapper.process("updates", chunk)]
    assert len(events) == 1
    assert events[0]["event"] == "todo_updated"
    assert json.loads(events[0]["data"])["items"][0]["text"] == "Step 1"


@pytest.mark.asyncio
async def test_same_todos_does_not_re_emit():
    from app.streaming.chunk_mapper import ChunkMapper
    mapper = ChunkMapper()
    chunk = {"main": {"todos": [{"text": "Step 1", "status": "pending"}]}}
    [ev async for ev in mapper.process("updates", chunk)]
    second = [ev async for ev in mapper.process("updates", chunk)]
    assert second == []


@pytest.mark.asyncio
async def test_new_file_in_files_dict_emits_file_saved():
    from app.streaming.chunk_mapper import ChunkMapper
    mapper = ChunkMapper()
    chunk = {"main": {"files": {"vfs://draft.md": "hello world"}}}
    events = [ev async for ev in mapper.process("updates", chunk)]
    assert len(events) == 1
    assert events[0]["event"] == "file_saved"
    payload = json.loads(events[0]["data"])
    assert payload["path"] == "vfs://draft.md"
    assert payload["preview"].startswith("hello")


@pytest.mark.asyncio
async def test_subagent_node_emits_started_then_completed():
    from app.streaming.chunk_mapper import ChunkMapper
    mapper = ChunkMapper()
    started = [ev async for ev in mapper.process(
        "updates", {"researcher": {"task": "Research X"}}
    )]
    assert started[0]["event"] == "subagent_started"
    completed = [ev async for ev in mapper.process(
        "updates", {"researcher": {"summary": "found X", "__end__": True}}
    )]
    assert completed[0]["event"] == "subagent_completed"


@pytest.mark.asyncio
async def test_first_chunk_with_both_task_and_summary_emits_only_started():
    """Regression: protects elif-not-if structure. A first-appearance chunk
    should always be treated as a start, even if it carries summary fields."""
    from app.streaming.chunk_mapper import ChunkMapper
    mapper = ChunkMapper()
    events = [ev async for ev in mapper.process(
        "updates",
        {"researcher": {"task": "X", "summary": "Y", "__end__": True}}
    )]
    kinds = [ev["event"] for ev in events]
    assert kinds == ["subagent_started"]
    assert "subagent_completed" not in kinds


@pytest.mark.asyncio
async def test_token_drop_below_70_pct_triggers_compression():
    from app.streaming.chunk_mapper import ChunkMapper
    mapper = ChunkMapper()
    # First snapshot
    [ev async for ev in mapper.process("values", {"messages": ["x" * 10000]})]
    # Second snapshot — much smaller
    events = [ev async for ev in mapper.process("values", {"messages": ["x" * 1000]})]
    assert any(ev["event"] == "compression_triggered" for ev in events)


@pytest.mark.asyncio
async def test_text_delta_only_after_report_phase():
    from langchain_core.messages import AIMessageChunk
    from app.streaming.chunk_mapper import ChunkMapper
    mapper = ChunkMapper()

    # Before critic completes, no text_delta
    msg = AIMessageChunk(content="hi")
    pre = [ev async for ev in mapper.process("messages", (msg, {}))]
    assert pre == []

    # Critic completes → report_phase = True
    [ev async for ev in mapper.process(
        "updates", {"critic": {"summary": "ok", "__end__": True}}
    )]

    # Now text_delta flows
    post = [ev async for ev in mapper.process("messages", (msg, {}))]
    assert any(ev["event"] == "text_delta" for ev in post)
```

- [ ] **Step 4.2.2: Run, confirm fail.**

- [ ] **Step 4.2.3: Implement `apps/api/app/streaming/chunk_mapper.py`:**

```python
import uuid
from typing import Any, AsyncIterator

import tiktoken

from app.config.settings import settings
from app.streaming import events

_enc = tiktoken.encoding_for_model("gpt-4o")


def _count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def _new_id() -> str:
    return uuid.uuid4().hex


def _estimate_state_tokens(snapshot: dict) -> int:
    total = 0
    for m in snapshot.get("messages", []):
        content = getattr(m, "content", m) if not isinstance(m, str) else m
        total += _count_tokens(str(content))
    for content in snapshot.get("files", {}).values():
        total += _count_tokens(content)
    return total


class ChunkMapper:
    def __init__(self) -> None:
        self._prev_files: dict[str, str] = {}
        self._prev_todos: list[dict] = []
        self._active_subagents: dict[str, str] = {}
        self._prev_token_count: int | None = None
        self._report_phase: bool = False

        # Public introspection for the router's synthetic-compression fallback
        self.saw_compression: bool = False
        self.peak_tokens: int = 0

    async def process(self, mode: str, chunk: Any) -> AsyncIterator[dict]:
        if mode == "updates":
            async for ev in self._handle_updates(chunk):
                yield ev
        elif mode == "messages":
            msg_chunk, _meta = chunk
            if self._report_phase and getattr(msg_chunk, "content", ""):
                yield events.text_delta(msg_chunk.content)
        elif mode == "values":
            async for ev in self._handle_values_snapshot(chunk):
                yield ev

    async def _handle_updates(self, chunk: dict) -> AsyncIterator[dict]:
        for node_name, update in chunk.items():
            if not isinstance(update, dict):
                continue

            if "todos" in update and update["todos"] != self._prev_todos:
                self._prev_todos = update["todos"]
                yield events.todo_updated(update["todos"])

            if "files" in update:
                for path, content in update["files"].items():
                    if self._prev_files.get(path) != content:
                        self._prev_files[path] = content
                        yield events.file_saved(
                            path=path,
                            size_tokens=_count_tokens(content),
                            preview=content[:500],
                        )

            if node_name in {"researcher", "critic"}:
                # elif (not two ifs) — a single chunk is treated as either
                # a start or an end, never both. Matches spec §7 semantics.
                if node_name not in self._active_subagents:
                    run_id = _new_id()
                    self._active_subagents[node_name] = run_id
                    yield events.subagent_started(
                        run_id, node_name, update.get("task", "")
                    )
                elif update.get("__end__") or update.get("summary"):
                    run_id = self._active_subagents.pop(node_name)
                    yield events.subagent_completed(
                        run_id, update.get("summary", "")
                    )
                    if node_name == "critic":
                        self._report_phase = True

    async def _handle_values_snapshot(self, snapshot: dict) -> AsyncIterator[dict]:
        current = _estimate_state_tokens(snapshot)
        self.peak_tokens = max(self.peak_tokens, current)
        if (
            self._prev_token_count
            and current < self._prev_token_count * settings.COMPRESSION_DETECTION_RATIO
        ):
            self.saw_compression = True
            yield events.compression_triggered(self._prev_token_count, current)
        self._prev_token_count = current
```

- [ ] **Step 4.2.4: Run, confirm pass.**

- [ ] **Step 4.2.5: Commit:**

```bash
git add apps/api/app/streaming/chunk_mapper.py apps/api/tests/unit/test_chunk_mapper.py
git commit -m "feat(api): stateful chunk mapper for LangGraph stream → SSE events"
```

---

### Task 4.3: Schemas + Router (TDD with E2E smoke first)

**Files:**
- Create: `apps/api/app/schemas/research.py`
- Create: `apps/api/app/routers/research.py`
- Modify: `apps/api/app/main.py` (register router)
- Create: `apps/api/tests/e2e/test_research_endpoint.py`

- [ ] **Step 4.3.1: Implement schema first (data structure prerequisite, no logic to TDD):**

```python
# apps/api/app/schemas/research.py
from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    thread_id: str | None = None
```

- [ ] **Step 4.3.2: Write failing E2E test** `apps/api/tests/e2e/test_research_endpoint.py`:

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_research_endpoint_streams_expected_event_sequence(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    async def fake_astream(*args, **kwargs):
        yield ("updates", {"main": {"todos": [{"text": "step1", "status": "pending"}]}})
        yield ("updates", {"researcher": {"task": "research X"}})
        yield ("updates", {"researcher": {"summary": "done", "__end__": True}})
        yield ("updates", {"critic": {"summary": "ok", "__end__": True}})

    fake_agent = MagicMock()
    fake_agent.astream = fake_astream
    fake_agent.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    # build_research_agent is imported INTO app.routers.research, so patch
    # the symbol in that namespace, not in app.services.agent_factory.
    with patch("app.routers.research.build_research_agent", return_value=fake_agent):
        from app.main import app
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            async with client.stream(
                "POST", "/research",
                json={"question": "compare frameworks"},
            ) as resp:
                events = []
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        events.append(line.split(":", 1)[1].strip())

    assert "stream_start" in events
    assert "todo_updated" in events
    assert "subagent_started" in events
    assert "subagent_completed" in events
    assert events[-1] == "stream_end"


@pytest.mark.asyncio
async def test_synthetic_compression_emitted_when_no_real_compression(monkeypatch):
    """When peak_tokens > 30k and no real compression seen, router emits
    a synthetic compression_triggered event before stream_end."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    async def fake_astream(*args, **kwargs):
        # Single huge values snapshot so peak_tokens > 30k, but no token drop
        yield ("values", {"messages": ["x" * 200_000], "files": {}})

    fake_agent = MagicMock()
    fake_agent.astream = fake_astream
    fake_agent.aget_state = AsyncMock(return_value=MagicMock(values={"usage": {}}))

    with patch("app.routers.research.build_research_agent", return_value=fake_agent):
        from app.main import app
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            async with client.stream(
                "POST", "/research", json={"question": "compare X"},
            ) as resp:
                events = [
                    line.split(":", 1)[1].strip()
                    async for line in resp.aiter_lines()
                    if line.startswith("event:")
                ]

    assert "compression_triggered" in events
```

- [ ] **Step 4.3.3: Run, confirm fail** (router doesn't exist yet):

```bash
cd apps/api && python -m pytest tests/e2e/test_research_endpoint.py -v
```

Expected: FAIL with ImportError or 404.

- [ ] **Step 4.3.4: Implement complete router** `apps/api/app/routers/research.py`:

```python
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.schemas.research import ResearchRequest
from app.services.agent_factory import build_research_agent
from app.streaming import events
from app.streaming.chunk_mapper import ChunkMapper

router = APIRouter(prefix="/research", tags=["research"])

SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS = 30_000


@router.post("")
async def research(payload: ResearchRequest):
    agent = build_research_agent()
    thread_id = payload.thread_id or "default-user"
    mapper = ChunkMapper()
    final_report_parts: list[str] = []

    async def generator():
        yield events.stream_start(thread_id)
        try:
            async for mode, chunk in agent.astream(
                {"messages": [{"role": "user", "content": payload.question}]},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode=["values", "messages", "updates"],
            ):
                async for ev in mapper.process(mode, chunk):
                    if ev["event"] == "text_delta":
                        final_report_parts.append(
                            json.loads(ev["data"])["content"]
                        )
                    yield ev

            # Synthetic-compression fallback (spec §9.1):
            # If no real compression was observed but session was large,
            # emit one synthetic event so Success Criterion #4 is observable.
            if (
                not mapper.saw_compression
                and mapper.peak_tokens > SYNTHETIC_COMPRESSION_THRESHOLD_TOKENS
            ):
                yield events.compression_triggered(
                    original_tokens=mapper.peak_tokens,
                    compressed_tokens=mapper.peak_tokens // 2,
                    synthetic=True,
                )

            final_state = await agent.aget_state(
                {"configurable": {"thread_id": thread_id}}
            )
            usage = final_state.values.get("usage", {})
            yield events.stream_end(
                final_report="".join(final_report_parts),
                usage=usage,
            )
        except Exception as e:  # noqa: BLE001 — surface any failure to client
            yield events.error(str(e), recoverable=False)

    return EventSourceResponse(generator())
```

- [ ] **Step 4.3.5: Modify `apps/api/app/main.py`** to include router:

```python
from app.routers import research as research_router
app.include_router(research_router.router)
```

- [ ] **Step 4.3.6: Run E2E test, confirm both pass:**

```bash
cd apps/api && python -m pytest tests/e2e/test_research_endpoint.py -v
```

Expected: 2 passed.

- [ ] **Step 4.3.7: Commit:**

```bash
git add apps/api/app/schemas apps/api/app/routers apps/api/app/main.py apps/api/tests/e2e
git commit -m "feat(api): research SSE endpoint with synthetic-compression fallback"
```

---

## Chunk 5: Frontend Foundation (Next.js + Hook + Parser + Proxy)

**Goal of chunk:** Frontend can consume SSE stream and update reducer state — verified via mock backend or live backend.

### Task 5.1: Initialize Next.js app + tooling

**Files:**
- Create: `apps/web/` (via `create-next-app`)
- Create: `apps/web/.prettierrc.json`
- Create: `apps/web/.prettierignore`
- Create: `apps/web/.env.example`
- Create: `apps/web/README.md`
- Modify: `apps/web/package.json` (scripts)

- [ ] **Step 5.1.1: Scaffold:**

```bash
cd apps && npx create-next-app@^14 web \
  --typescript --tailwind --app --no-src-dir --eslint --no-import-alias
```

(Next.js generates `.eslintrc.json` extending `next/core-web-vitals` automatically.)

- [ ] **Step 5.1.2: Install Prettier + Tailwind class-sorter plugin + ESLint-Prettier interop:**

```bash
cd apps/web && npm i -D prettier prettier-plugin-tailwindcss eslint-config-prettier
```

Then extend `apps/web/.eslintrc.json` to disable any ESLint rules that would conflict with Prettier (must be the LAST entry in `extends`):

```json
{
  "extends": ["next/core-web-vitals", "prettier"]
}
```

- [ ] **Step 5.1.3: Create `apps/web/.prettierrc.json`:**

```json
{
  "semi": true,
  "singleQuote": false,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2,
  "arrowParens": "always",
  "plugins": ["prettier-plugin-tailwindcss"]
}
```

- [ ] **Step 5.1.4: Create `apps/web/.prettierignore`:**

```
.next/
out/
node_modules/
public/
*.lock
package-lock.json
```

- [ ] **Step 5.1.5: Add scripts to `apps/web/package.json`** (merge into existing `scripts` object):

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "format": "prettier --write .",
    "format:check": "prettier --check .",
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

- [ ] **Step 5.1.6: Create `apps/web/.env.example`:**

```
API_URL=http://localhost:8000
```

Then copy locally:

```bash
cd apps/web && cp .env.example .env.local
```

- [ ] **Step 5.1.7: Scaffold `apps/web/README.md`** (filled out further in Chunk 6):

````markdown
# Web — Deep Agents Research Dashboard

Next.js 14 (App Router) frontend that consumes the FastAPI SSE stream and visualizes all 5 Deep Agents capabilities live.

## Run

```bash
npm install
cp .env.example .env.local   # set API_URL
npm run dev                  # http://localhost:3000/research
```

## Test

```bash
npm test                # vitest run (sseParser + reducer)
npm run test:watch
```

## Lint / Format

```bash
npm run lint            # next lint (ESLint)
npm run format          # prettier write
npm run format:check    # prettier check (CI)
```

## Architecture

- `app/research/page.tsx` — dashboard route
- `lib/useResearchStream.ts` — SSE consumer hook + reducer
- `lib/sseParser.ts` — pure SSE frame parser
- `app/api/research/route.ts` — server-side proxy to FastAPI

See [docs/2026-04-13-deep-agents-research-assistant-design.md](../../docs/2026-04-13-deep-agents-research-assistant-design.md) section 8 for component design.
````

- [ ] **Step 5.1.8: Verify lint + format run cleanly:**

```bash
cd apps/web && npm run lint && npm run format:check
```

Expected: both exit 0 (or `format:check` flags scaffolded files — run `npm run format` once to normalize).

- [ ] **Step 5.1.9: Commit:**

```bash
git add apps/web
git commit -m "feat(web): scaffold Next.js 14 + TypeScript + Tailwind + Prettier"
```

---

### Task 5.2: SSE parser utility (TDD)

**Files:**
- Create: `apps/web/lib/sseParser.ts`
- Create: `apps/web/lib/sseParser.test.ts`
- Create: `apps/web/vitest.config.ts` (if not present, use jest setup that works with ts)

- [ ] **Step 5.2.1: Add vitest dev dep:**

```bash
cd apps/web && npm i -D vitest @testing-library/react @testing-library/dom jsdom
```

Add to `package.json` scripts: `"test": "vitest run"`.

Create `vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
export default defineConfig({ test: { environment: "jsdom" } });
```

- [ ] **Step 5.2.2: Write failing test** `apps/web/lib/sseParser.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { consumeFrames, leftoverAfterFrames } from "./sseParser";

describe("sseParser", () => {
  it("parses a single complete frame", () => {
    const buf = "event: foo\ndata: {\"x\":1}\n\n";
    expect(consumeFrames(buf)).toEqual([{ event: "foo", data: { x: 1 } }]);
  });

  it("returns leftover for incomplete frame", () => {
    const buf = "event: foo\ndata: {\"x\":1}\n\nevent: bar\ndata: ";
    const frames = consumeFrames(buf);
    expect(frames).toHaveLength(1);
    expect(leftoverAfterFrames(buf)).toBe("event: bar\ndata: ");
  });

  it("handles multi-line data", () => {
    const buf = "event: r\ndata: {\"a\":1}\n\nevent: r\ndata: {\"a\":2}\n\n";
    expect(consumeFrames(buf)).toHaveLength(2);
  });
});
```

- [ ] **Step 5.2.3: Run, confirm fail.**

- [ ] **Step 5.2.4: Implement `apps/web/lib/sseParser.ts`:**

```ts
export type SSEFrame = { event: string; data: unknown };

export function consumeFrames(buffer: string): SSEFrame[] {
  const frames: SSEFrame[] = [];
  const parts = buffer.split("\n\n");
  // last part may be incomplete — only parse all but the last
  for (let i = 0; i < parts.length - 1; i++) {
    const block = parts[i];
    let event = "message";
    let dataStr = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
    }
    if (dataStr) {
      try {
        frames.push({ event, data: JSON.parse(dataStr) });
      } catch {
        frames.push({ event, data: dataStr });
      }
    }
  }
  return frames;
}

export function leftoverAfterFrames(buffer: string): string {
  const parts = buffer.split("\n\n");
  return parts[parts.length - 1];
}
```

- [ ] **Step 5.2.5: Run, confirm pass.**

- [ ] **Step 5.2.6: Commit:**

```bash
git add apps/web/lib/sseParser.ts apps/web/lib/sseParser.test.ts apps/web/vitest.config.ts apps/web/package.json apps/web/package-lock.json
git commit -m "feat(web): SSE frame parser utility"
```

---

### Task 5.3: TypeScript types matching backend events

**Files:**
- Create: `apps/web/lib/types.ts`

- [ ] **Step 5.3.1: Implement:**

```ts
export type TodoStatus = "pending" | "in_progress" | "done";
export type TodoItem = { text: string; status: TodoStatus };
export type FileRef = { path: string; size_tokens: number; preview: string };
export type SubagentRun = {
  id: string; name: string; task: string;
  status: "running" | "done"; summary?: string;
};
export type CompressionEvent = {
  original_tokens: number; compressed_tokens: number; synthetic?: boolean;
};

export type SSEEventMap = {
  stream_start: { thread_id: string; started_at: string };
  todo_updated: { items: TodoItem[] };
  file_saved: { path: string; size_tokens: number; preview: string };
  subagent_started: { id: string; name: string; task: string };
  subagent_completed: { id: string; summary: string };
  compression_triggered: CompressionEvent;
  text_delta: { content: string };
  memory_updated: { namespace: string; key: string };
  error: { message: string; recoverable: boolean };
  stream_end: { final_report: string; usage: Record<string, unknown> };
};
```

- [ ] **Step 5.3.2: Commit:**

```bash
git add apps/web/lib/types.ts
git commit -m "feat(web): typed SSE event payload definitions"
```

---

### Task 5.4: useResearchStream hook

**Files:**
- Create: `apps/web/lib/useResearchStream.ts`

- [ ] **Step 5.4.1: Implement:**

```ts
"use client";
import { useReducer, useRef } from "react";
import { consumeFrames, leftoverAfterFrames, SSEFrame } from "./sseParser";
import {
  TodoItem, FileRef, SubagentRun, CompressionEvent,
} from "./types";

export type ResearchState = {
  todos: TodoItem[];
  files: FileRef[];
  subagents: Record<string, SubagentRun>;
  compressions: CompressionEvent[];
  report: string;
  status: "idle" | "streaming" | "done" | "error";
  error?: string;
};

export const initial: ResearchState = {
  todos: [], files: [], subagents: {}, compressions: [],
  report: "", status: "idle",
};

export function reducer(state: ResearchState, frame: SSEFrame): ResearchState {
  const data = frame.data as any;
  switch (frame.event) {
    case "stream_start":
      return { ...initial, status: "streaming" };
    case "todo_updated":
      return { ...state, todos: data.items };
    case "file_saved":
      return { ...state, files: [...state.files.filter(f => f.path !== data.path), data] };
    case "subagent_started":
      return { ...state, subagents: { ...state.subagents,
        [data.id]: { ...data, status: "running" } } };
    case "subagent_completed":
      return { ...state, subagents: { ...state.subagents,
        [data.id]: { ...state.subagents[data.id], status: "done", summary: data.summary } } };
    case "compression_triggered":
      return { ...state, compressions: [...state.compressions, data] };
    case "text_delta":
      return { ...state, report: state.report + data.content };
    case "error":
      return { ...state, status: "error", error: data.message };
    case "stream_end":
      return { ...state, status: "done", report: data.final_report || state.report };
    default:
      return state;
  }
}

export function useResearchStream() {
  const [state, dispatch] = useReducer(reducer, initial);
  const controller = useRef<AbortController | null>(null);

  async function start(question: string) {
    controller.current?.abort();
    controller.current = new AbortController();
    const res = await fetch("/api/research", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, thread_id: "default-user" }),
      signal: controller.current.signal,
    });
    if (!res.body) return;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      for (const frame of consumeFrames(buf)) dispatch(frame);
      buf = leftoverAfterFrames(buf);
    }
  }

  function stop() {
    controller.current?.abort();
  }

  return { state, start, stop };
}
```

- [ ] **Step 5.4.2: Write reducer test** `apps/web/lib/useResearchStream.test.ts`:

```ts
import { describe, expect, it } from "vitest";
// Reducer is module-private; export it for testability OR re-import via test-only
// surface. For simplicity, refactor useResearchStream.ts to also export `reducer`
// and `initial` (named exports), then:
import { reducer, initial } from "./useResearchStream";

describe("research reducer", () => {
  it("stream_start resets to streaming state", () => {
    const after = reducer({ ...initial, report: "old" }, {
      event: "stream_start", data: { thread_id: "t", started_at: "now" }
    });
    expect(after.status).toBe("streaming");
    expect(after.report).toBe("");
  });

  it("todo_updated replaces items", () => {
    const after = reducer(initial, {
      event: "todo_updated",
      data: { items: [{ text: "a", status: "pending" }] }
    });
    expect(after.todos).toHaveLength(1);
  });

  it("file_saved upserts by path (no duplicates)", () => {
    let s = reducer(initial, {
      event: "file_saved",
      data: { path: "vfs://a", size_tokens: 100, preview: "x" }
    });
    s = reducer(s, {
      event: "file_saved",
      data: { path: "vfs://a", size_tokens: 200, preview: "x" }
    });
    expect(s.files).toHaveLength(1);
    expect(s.files[0].size_tokens).toBe(200);
  });

  it("subagent_started then subagent_completed updates same id", () => {
    let s = reducer(initial, {
      event: "subagent_started",
      data: { id: "r1", name: "researcher", task: "X" }
    });
    expect(s.subagents["r1"].status).toBe("running");
    s = reducer(s, {
      event: "subagent_completed",
      data: { id: "r1", summary: "done" }
    });
    expect(s.subagents["r1"].status).toBe("done");
    expect(s.subagents["r1"].summary).toBe("done");
  });

  it("text_delta appends to report", () => {
    let s = reducer(initial, { event: "text_delta", data: { content: "Hello " } });
    s = reducer(s, { event: "text_delta", data: { content: "world" } });
    expect(s.report).toBe("Hello world");
  });

  it("compression_triggered appends events", () => {
    const s = reducer(initial, {
      event: "compression_triggered",
      data: { original_tokens: 100, compressed_tokens: 50, synthetic: true }
    });
    expect(s.compressions).toHaveLength(1);
    expect(s.compressions[0].synthetic).toBe(true);
  });

  it("error sets error status and message", () => {
    const s = reducer(initial, {
      event: "error", data: { message: "boom", recoverable: false }
    });
    expect(s.status).toBe("error");
    expect(s.error).toBe("boom");
  });

  it("stream_end transitions to done with final_report override", () => {
    const s = reducer(
      { ...initial, report: "partial" },
      { event: "stream_end", data: { final_report: "complete", usage: {} } }
    );
    expect(s.status).toBe("done");
    expect(s.report).toBe("complete");
  });

  it("unknown event is a no-op", () => {
    const s = reducer(initial, { event: "unknown_xyz", data: {} } as any);
    expect(s).toBe(initial);
  });
});
```

(`reducer` and `initial` are already exported from `useResearchStream.ts` per Step 5.4.1.)

- [ ] **Step 5.4.3: Run, confirm pass:**

```bash
cd apps/web && npm test
```

Expected: all reducer tests pass plus prior `sseParser` tests.

- [ ] **Step 5.4.4: Commit:**

```bash
git add apps/web/lib/useResearchStream.ts apps/web/lib/useResearchStream.test.ts
git commit -m "feat(web): useResearchStream hook + reducer with full test coverage"
```

---

### Task 5.5: API proxy route

**Files:**
- Create: `apps/web/app/api/research/route.ts`

- [ ] **Step 5.5.1: Implement:**

```ts
export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = await req.text();
  const upstream = await fetch(`${process.env.API_URL}/research`, {
    method: "POST",
    body,
    headers: { "content-type": "application/json" },
  });
  return new Response(upstream.body, {
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      "connection": "keep-alive",
    },
  });
}
```

- [ ] **Step 5.5.2: Commit:**

```bash
git add apps/web/app/api
git commit -m "feat(web): SSE proxy route to FastAPI backend"
```

---

## Chunk 6: Dashboard Components + E2E Demo Verification

**Goal of chunk:** Full dashboard renders all 5 capabilities visibly during a real research session.

### Task 6.1: Dumb presentational components

**Files:**
- Create: `apps/web/app/research/components/QuestionForm.tsx`
- Create: `apps/web/app/research/components/TodoList.tsx`
- Create: `apps/web/app/research/components/FileList.tsx`
- Create: `apps/web/app/research/components/SubagentPanel.tsx`
- Create: `apps/web/app/research/components/CompressionBadge.tsx`
- Create: `apps/web/app/research/components/ReportView.tsx`

- [ ] **Step 6.1.1: `QuestionForm.tsx`:**

```tsx
"use client";
import { useState } from "react";

export function QuestionForm({ onSubmit, disabled }: {
  onSubmit: (q: string) => void; disabled: boolean;
}) {
  const [q, setQ] = useState("");
  return (
    <form
      className="flex gap-2 p-4 border-b"
      onSubmit={(e) => { e.preventDefault(); if (q.trim()) onSubmit(q.trim()); }}
    >
      <input
        className="flex-1 border rounded px-3 py-2"
        placeholder="Ask a research question..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
        disabled={disabled}
      />
      <button
        className="px-4 py-2 bg-blue-600 text-white rounded disabled:opacity-50"
        disabled={disabled || !q.trim()}
      >Start</button>
    </form>
  );
}
```

- [ ] **Step 6.1.2: `TodoList.tsx`:**

```tsx
import { TodoItem } from "@/lib/types";

const ICON = { pending: "⏳", in_progress: "▶", done: "✓" } as const;

export function TodoList({ items }: { items: TodoItem[] }) {
  if (items.length === 0) return <Empty label="No plan yet" />;
  return (
    <Section title="📋 To-do">
      <ul className="space-y-1 text-sm">
        {items.map((t, i) => (
          <li key={i} className={t.status === "done" ? "opacity-50" : ""}>
            <span className="mr-2">{ICON[t.status]}</span>{t.text}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="p-3 border-b"><h3 className="font-semibold mb-2">{title}</h3>{children}</div>;
}
function Empty({ label }: { label: string }) {
  return <div className="p-3 border-b text-sm text-gray-400">{label}</div>;
}
```

- [ ] **Step 6.1.3: `FileList.tsx`:**

```tsx
import { FileRef } from "@/lib/types";

export function FileList({ files }: { files: FileRef[] }) {
  if (files.length === 0) return null;
  return (
    <div className="p-3 border-b">
      <h3 className="font-semibold mb-2">📁 Files (vFS)</h3>
      <ul className="space-y-1 text-sm font-mono">
        {files.map((f) => (
          <li key={f.path} title={f.preview}>
            {f.path} <span className="text-gray-400">({f.size_tokens.toLocaleString()} tok)</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 6.1.4: `CompressionBadge.tsx`:**

```tsx
import { CompressionEvent } from "@/lib/types";

export function CompressionBadge({ events }: { events: CompressionEvent[] }) {
  if (events.length === 0) return null;
  const synthetic = events.some(e => e.synthetic);
  return (
    <span
      className="ml-2 text-xs bg-purple-100 text-purple-800 px-2 py-0.5 rounded"
      title={synthetic ? "Estimated (synthetic)" : "Detected from token drop"}
    >
      🗜 {events.length} compression{events.length > 1 ? "s" : ""}
    </span>
  );
}
```

- [ ] **Step 6.1.5: `SubagentPanel.tsx`:**

```tsx
import { SubagentRun, CompressionEvent } from "@/lib/types";
import { CompressionBadge } from "./CompressionBadge";

export function SubagentPanel({ runs, compressions }: {
  runs: Record<string, SubagentRun>; compressions: CompressionEvent[];
}) {
  const list = Object.values(runs);
  return (
    <div className="p-3 border-b">
      <h3 className="font-semibold mb-2">
        🤖 Subagents <CompressionBadge events={compressions} />
      </h3>
      {list.length === 0
        ? <div className="text-sm text-gray-400">None spawned yet</div>
        : <ul className="space-y-1 text-sm">
            {list.map((r) => (
              <li key={r.id}>
                <span className="font-mono">{r.name}</span>{" "}
                <span className="text-gray-500">{r.task}</span>{" "}
                <span>{r.status === "done" ? "✓" : "⏳"}</span>
              </li>
            ))}
          </ul>}
    </div>
  );
}
```

- [ ] **Step 6.1.6: `ReportView.tsx`:**

```tsx
export function ReportView({ text }: { text: string }) {
  return (
    <div className="p-4 overflow-auto h-full">
      <h3 className="font-semibold mb-2">📄 Report</h3>
      <pre className="whitespace-pre-wrap font-sans text-sm">{text || "—"}</pre>
    </div>
  );
}
```

- [ ] **Step 6.1.7: Commit:**

```bash
git add apps/web/app/research/components
git commit -m "feat(web): dashboard components for 5 deep-agents capabilities"
```

---

### Task 6.2: Research dashboard page

**Files:**
- Create: `apps/web/app/research/page.tsx`

- [ ] **Step 6.2.1: Implement:**

```tsx
"use client";
import { useResearchStream } from "@/lib/useResearchStream";
import { QuestionForm } from "./components/QuestionForm";
import { TodoList } from "./components/TodoList";
import { FileList } from "./components/FileList";
import { SubagentPanel } from "./components/SubagentPanel";
import { ReportView } from "./components/ReportView";

export default function ResearchPage() {
  const { state, start } = useResearchStream();
  const busy = state.status === "streaming";
  return (
    <div className="h-screen flex flex-col">
      <header className="px-4 py-3 border-b">
        <h1 className="text-lg font-semibold">Deep Agents Research Assistant</h1>
      </header>
      <QuestionForm onSubmit={start} disabled={busy} />
      <main className="flex flex-1 min-h-0">
        <aside className="w-80 border-r overflow-y-auto">
          <TodoList items={state.todos} />
          <FileList files={state.files} />
          <SubagentPanel runs={state.subagents} compressions={state.compressions} />
        </aside>
        <section className="flex-1 min-w-0">
          <ReportView text={state.report} />
        </section>
      </main>
      {state.error && (
        <div className="p-3 bg-red-100 text-red-800 text-sm">{state.error}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 6.2.2: Commit:**

```bash
git add apps/web/app/research/page.tsx
git commit -m "feat(web): research dashboard page composing all panels"
```

---

### Task 6.3: End-to-end demo verification

**Goal:** Walk through Success Criteria (spec §12) on a live system.

**Files:**
- Create: `docs/demo-verification.md` (verification checklist with results)

- [ ] **Step 6.3.1: Start backend** with real keys (from your local secrets):

```bash
cd apps/api && source .venv/bin/activate && \
  uvicorn app.main:app --reload --port 8000
```

Expected: starts cleanly, `data/checkpoints.sqlite` created.

- [ ] **Step 6.3.2: Start frontend in another terminal:**

```bash
cd apps/web && npm run dev
```

Expected: ready on `http://localhost:3000`.

- [ ] **Step 6.3.3: Open `http://localhost:3000/research`** and submit:

> *"Compare LangGraph, CrewAI, and AutoGen as agentic AI frameworks."*

- [ ] **Step 6.3.4: Verify each capability appears on dashboard:**

| Capability | Visible signal | Pass? |
|---|---|---|
| Planning | TodoList shows 3-5 items, statuses update | [ ] |
| Virtual FS | FileList shows ≥1 saved file with token count | [ ] |
| Subagents | SubagentPanel shows ≥2 researcher runs | [ ] |
| Compression | CompressionBadge shows ≥1 (real or synthetic) | [ ] |
| Report streams | ReportView updates token-by-token | [ ] |

- [ ] **Step 6.3.5: Test cross-conversation memory.** Submit a SECOND question:

> *"What did I just research? Suggest a follow-up topic."*

Expected: agent references prior topic from store. Pass criterion #5 [ ].

- [ ] **Step 6.3.6: Test LLM swap.** Stop backend, edit `.env`:

```diff
- LLM_PROVIDER=anthropic
+ LLM_PROVIDER=openai
+ OPENAI_API_KEY=sk-...
```

Restart backend, run a short query. Expected: works without code changes. Pass criterion #6 [ ].

- [ ] **Step 6.3.7: Record verification results in `docs/demo-verification.md`** with screenshots if possible. Commit:

```bash
git add docs/demo-verification.md
git commit -m "docs: demo verification — all 5 deep-agents capabilities visible"
```

---

### Task 6.4: Polish READMEs after live verification

**Files:**
- Modify: `README.md` (root)
- Modify: `apps/api/README.md`
- Modify: `apps/web/README.md`
- Modify: `CONTRIBUTING.md` (if any conventions changed during build)

- [ ] **Step 6.4.1: Update root `README.md`** with:
  - **Status badge / version**: e.g. "Demo — 2026-04-13"
  - **Screenshot** from Step 6.3.7 (place under `docs/screenshots/dashboard.png`, link from README)
  - **"Known limitations"** section listing items from spec §11 (no auth, in-memory store, etc.)
  - **Troubleshooting** section: Tavily 429, Anthropic 529 overload, missing keys
  - **Verified versions** table (Python, Node, key library versions actually run during demo)

- [ ] **Step 6.4.2: Update `apps/api/README.md`** with:
  - **Real example response** (truncated SSE event stream from a successful run)
  - **Provider swap walkthrough** (concrete `.env` diff for switching to OpenAI)
  - **Test coverage report snippet** (`pytest --cov` output)

- [ ] **Step 6.4.3: Update `apps/web/README.md`** with:
  - **Screenshot of dashboard** with all 5 capability panels populated
  - **State shape diagram** (`ResearchState` fields → which event drives which)
  - **Note on `EventSource`-vs-`fetch`** — link to spec §8 transport rationale

- [ ] **Step 6.4.4: Update `CONTRIBUTING.md`** if any convention drifted during build (e.g., new commit scope discovered, new lint rule added).

- [ ] **Step 6.4.5: Verify all READMEs render correctly:**

```bash
# Open in your markdown viewer of choice or:
cat README.md && cat apps/api/README.md && cat apps/web/README.md
```

Look for: broken relative links, missing image paths, leftover "TODO" markers.

- [ ] **Step 6.4.6: Final lint + format pass on the whole repo:**

```bash
cd apps/api && ruff check . && ruff format --check . && mypy app/
cd ../web && npm run lint && npm run format:check && npm test
```

Expected: all green.

- [ ] **Step 6.4.7: Ensure screenshot directory exists, then commit:**

```bash
mkdir -p docs/screenshots
# (drop your screenshot file(s) here, e.g. dashboard.png)
git add README.md CONTRIBUTING.md apps/api/README.md apps/web/README.md docs/screenshots
git commit -m "docs: polish READMEs after live demo verification"
```

---

## Done Criteria (whole plan)

- All 7 chunks (0–6) committed
- All unit + integration + e2e tests pass
- `ruff check`, `ruff format --check`, `mypy app/`, `npm run lint`, `npm run format:check` all green
- `docs/demo-verification.md` records all 5 success criteria as PASS
- Root `README.md`, `apps/api/README.md`, `apps/web/README.md`, `CONTRIBUTING.md` are filled out (no TODOs)
- `.editorconfig`, `.gitignore`, `.gitattributes` enforced repo-wide

## Out of Plan (deferred per spec §11)

- Authentication
- Postgres
- Multi-user UI
- Deployment / Docker
- Markdown rendering polish in ReportView (currently `<pre>`)

If any of these become priorities, they're sub-projects and need their own brainstorm → spec → plan cycle.
