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
