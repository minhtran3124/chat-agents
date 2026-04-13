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
