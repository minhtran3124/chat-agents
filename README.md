# Deep Agents Research Assistant

A FastAPI + Next.js 14 demo showcasing multi-agent orchestration with [LangChain Deep Agents](https://github.com/langchain-ai/deepagents) and [LangGraph](https://github.com/langchain-ai/langgraph).

Two endpoints: **`POST /chat`** routes through a classifier to one of 6 specialists; **`POST /research`** bypasses routing and runs the full deep-research pipeline directly. Both stream progress over SSE to a live dashboard.

## Screenshots

![Dashboard overview](./docs/screenshots/dashboard.png)
![Plan completed](./docs/screenshots/plan.png)
![Researchers panel](./docs/screenshots/researchers.png)
![Files panel](./docs/screenshots/files.png)

## Quickstart

**Backend**
```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env       # fill in OPENAI_API_KEY and TAVILY_API_KEY
uvicorn app.main:app --reload --port 8000
```

**Frontend** (separate terminal)
```bash
cd apps/web
npm install
cp .env.example .env.local # set API_URL=http://localhost:8000
npm run dev                # http://localhost:3000/research
```

## More Detail

- [Backend README](./apps/api/README.md) — architecture, agents, SSE events, config
- [Frontend README](./apps/web/README.md) — components, SSE client, testing
- [Contributing guide](./CONTRIBUTING.md)
- [Design spec](./docs/specs/2026-04-13-deep-agents-research-assistant-design.md)
