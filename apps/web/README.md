# Web — Deep Agents Research Dashboard

Next.js 14 (App Router) frontend that consumes SSE streams from the FastAPI backend and visualises all agent activity live.

## Run

```bash
npm install
cp .env.example .env.local   # set API_URL=http://localhost:8000
npm run dev                  # http://localhost:3000/research
```

## Architecture

### Directory Structure

```
app/
├── research/
│   ├── page.tsx                  # Main dashboard route
│   └── components/
│       ├── QuestionForm.tsx       # Question input + submit
│       ├── TodoList.tsx           # Plan steps (pending / in_progress / completed)
│       ├── SubagentPanel.tsx      # Researcher cards + compression badge
│       ├── FileList.tsx           # Virtual FS browser
│       ├── ReportView.tsx         # Final report (react-markdown)
│       ├── RoutedIntentBadge.tsx  # Classifier intent display
│       ├── StatusBadge.tsx        # idle | loading | streaming | done | error
│       ├── AskedCard.tsx          # Pinned acknowledgment card
│       ├── SubagentToast.tsx      # Ephemeral 5-second toasts
│       └── CompressionBadge.tsx  # "Memory refreshed ×N" counter
├── api/
│   └── research/route.ts         # Server-side proxy → FastAPI /research
├── layout.tsx
├── page.tsx                      # Redirects to /research
└── globals.css                   # Tailwind base + animations
lib/
├── useResearchStream.ts          # SSE consumer hook + reducer
├── sseParser.ts                  # Pure SSE frame parser (RFC 9110)
└── types.ts                      # SSEEventMap discriminated union
```

### SSE Client Flow

```
useResearchStream.start(question)
  → fetch POST /api/research   (Next.js proxy → FastAPI)
  → read response.body as ReadableStream
  → sseParser.consumeFrames()  (parse text/event-stream frames)
  → dispatch each SSEFrame to reducer
  → React state updated → UI re-renders
```

No `EventSource` — uses native `fetch` so a POST body with `thread_id` and `prompt_versions` can be sent.

### State Shape (`useResearchStream`)

```ts
type ResearchState = {
  status: "idle" | "loading" | "streaming" | "done" | "error";
  question: string;
  threadId: string | null;
  routedIntent: string | null;
  todos: TodoItem[];
  subagents: Record<string, SubagentInfo>;
  files: FileItem[];
  compressions: CompressionEvent[];
  report: string;
  error: string | null;
};
```

The reducer handles all 11 SSE event types as pure transitions — same event + same state always produces the same next state.

### SSE Parser (`lib/sseParser.ts`)

- Parses `text/event-stream` spec: `\r\n\r\n` / `\n\n` frame separators, `event:` and `data:` line prefixes
- `consumeFrames(buffer)` → `SSEFrame[]` (fully parsed frames)
- `leftoverAfterFrames(buffer)` → remaining incomplete bytes (appended on next chunk)
- Pure functions, no side effects — straightforward to unit test

### Type Safety (`lib/types.ts`)

All SSE events are modelled as a discriminated union:

```ts
type SSEEventMap = {
  stream_start:          { thread_id: string; started_at: string };
  intent_classified:     { intent: string; confidence: number; fallback_used: boolean };
  todo_updated:          { items: TodoItem[] };
  subagent_started:      { id: string; name: string; task: string };
  subagent_completed:    { id: string; summary: string };
  file_saved:            { path: string; size_tokens: number; preview: string };
  compression_triggered: { original_tokens: number; compressed_tokens: number; synthetic: boolean };
  text_delta:            { content: string };
  memory_updated:        { namespace: string; key: string };
  error:                 { message: string; recoverable: boolean };
  stream_end:            { final_report: string; usage: UsageInfo; versions_used: Record<string, string> };
};
```

Any new backend event type **must** be added here and handled in the reducer.

### Components

**No component library** — all UI is hand-built with Tailwind 3.4 utilities.

| Component | Receives | Renders |
| :-------- | :------- | :------ |
| `QuestionForm` | `onSubmit`, `disabled` | Textarea + submit button |
| `TodoList` | `todos: TodoItem[]` | Steps with status icons and strikethrough |
| `SubagentPanel` | `subagents`, `compressions` | Researcher cards + compression counter |
| `FileList` | `files: FileItem[]` | File rows with path and token count |
| `ReportView` | `report: string`, `status` | `react-markdown` with `remark-gfm` |
| `RoutedIntentBadge` | `intent: string \| null` | Pill showing classified intent |
| `StatusBadge` | `status` | Colour-coded connection state |
| `AskedCard` | `question`, `status` | Pinned card shown immediately after submit |
| `SubagentToast` | `events[]` | Auto-dismiss toast stack (5 s TTL) |
| `CompressionBadge` | `count: number` | "Memory refreshed ×N" badge |

### Routing & Server Components

- `/` → redirects to `/research`
- `/research` → **Client Component** (uses `useResearchStream` hook, needs `"use client"`)
- `/api/research` → **Node.js Route Handler** proxies POST body + streams response back

### Styling Conventions

- Tailwind 3.4 with `@tailwindcss/typography` (the `prose` class renders the markdown report)
- Custom theme colours defined in `tailwind.config.ts`: `cream`, `ink`, `terracotta`, and others
- Class order enforced by `prettier-plugin-tailwindcss` — run `npm run format` instead of hand-sorting

## Test

```bash
npm test              # vitest run
npm run test:watch    # watch mode
```

Test files sit next to the code they test:

| File | Tests |
| :--- | :---- |
| `lib/sseParser.test.ts` | Frame parsing, CRLF/LF variants, multiline data, incomplete buffers |
| `lib/useResearchStream.test.ts` | Reducer transitions for all event types |
| `app/research/components/ReportView.test.tsx` | Markdown render, status states |

Testing priorities: query by role > label > text > testId. Mock `sseParser` when testing the hook; mock the hook when testing components.

## Lint / Format

```bash
npm run lint           # ESLint (eslint-config-next + eslint-config-prettier)
npm run format         # prettier --write
npm run format:check   # CI check
```

## Environment Variables

| Variable | Required | Description |
| :------- | :------- | :---------- |
| `API_URL` | Yes | Base URL of the FastAPI backend (e.g. `http://localhost:8000`) |

`API_URL` has no `NEXT_PUBLIC_` prefix — it is server-only and never exposed to the browser.
