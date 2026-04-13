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
