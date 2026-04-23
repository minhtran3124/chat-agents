# API Architecture — Deep Agent Internals

The research agent inside `apps/api/`: three roles coordinating through one shared state object, built on `deepagents` + LangGraph.

Wired in `app/services/agent_factory.py`. Contracts live in `prompts/main/v2.md`, `prompts/researcher/v1.md`, `prompts/critic/v1.md`.

---

## 1. The Picture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       deepagents  (LangGraph)                            │
│                                                                          │
│   ┌────────────────────────────────────────────────────────────────┐     │
│   │               MAIN AGENT  (orchestrator)                       │     │
│   │   model : Sonnet 4.6    prompt : main/v2                       │     │
│   │   tools : internet_search + write_todos, write_file,           │     │
│   │           edit_file, read_file, ls, task                       │     │
│   └─────┬────────────────────────┬────────────────────────┬────────┘     │
│         │ task("researcher")     │ write_file("draft.md") │ task("critic")│
│         ▼                        ▼                        ▼              │
│   ┌──────────────┐       ┌────────────────┐      ┌───────────────────┐   │
│   │ RESEARCHER   │       │  SHARED STATE  │      │    CRITIC         │   │
│   │ model: Haiku │ ────▶ │  messages[]    │ ◀─── │ model: Haiku      │   │
│   │ tools:       │ reads │  todos[]       │ read │ tools: (none)     │   │
│   │  internet_   │ /     │  files{}       │ only │ reads draft.md    │   │
│   │  search      │ writes│  usage{}       │      │ from files{}      │   │
│   └──────────────┘       └────────┬───────┘      └───────────────────┘   │
│                                   │                                      │
│                                   ▼  snapshot after every node           │
│                       AsyncSqliteSaver  (checkpoints.sqlite, per thread) │
│                       InMemoryStore     (cross-thread prefs / topics)    │
└──────────────────────────────────────────────────────────────────────────┘
```

Two sub-agents report to one orchestrator. Everyone edits the same state. The checkpointer snapshots it per `thread_id`.

---

## 2. Agent Roster

| Role       | Prompt          | Model          | Tools                                           |
| :--------- | :-------------- | :------------- | :---------------------------------------------- |
| **Main**       | `main/v2`       | Sonnet 4.6     | `internet_search` + all deepagents built-ins    |
| **Researcher** | `researcher/v1` | Haiku 4.5      | `internet_search`                               |
| **Critic**     | `critic/v1`     | Haiku 4.5      | *none* (read-only over shared state)            |

**Why the split:** Main plans and synthesizes on the capable model; sub-agents are high-volume narrow tasks on the cheap model — a 5–10× cost lever.

---

## 3. How Delegation Actually Works

Sub-agents are spawned through a **built-in `task` tool**, not a separate router. The main agent emits a tool call:

```
task(subagent_type="researcher", description=<topic>)
```

`deepagents` intercepts it, runs the chosen sub-agent's LangGraph seeded with the parent's state, and returns the sub-agent's final assistant message as the tool's result.

**The virtual filesystem is just a dict in shared state** (`state.files: dict[str, str]`). No disk. When the researcher calls `write_file("raw.md", ...)`, the file lands in the **parent's** `files` channel — which is why the critic can later `read_file("draft.md")` without anything being passed as an argument.

Sub-agent outputs therefore travel on **two channels simultaneously**:
- **Narrative summary** → returned as the `task` tool's result.
- **Artifacts** (raw search dumps, edits) → already sitting in shared `files` before the summary returns.

---

## 4. Orchestration Script (`main/v2`)

```
1. write_todos([3–5 sub-topics, pending])
2. store.get("preferences")                     ← cross-thread memory
3. for each todo:
     a. write_todos(... mark "in_progress")
     b. task("researcher", <topic + focus>)
          └─ 2–4 internet_search calls
          └─ write_file("<slug>.md", raw results)
          └─ returns 150-word summary w/ citations
     c. write_todos(... mark "completed")
4. write_file("draft.md", synthesized report)
5. task("critic", "review draft.md")
          └─ read_file("draft.md")
          └─ returns bulleted issue list
6. store.put("topics" / "preferences")
7. Final assistant message = revised report INLINE (no write_file).
```

**Two policies baked into the prompt:**

- **Final report is inline text, not a file.** v2 forbids writing `final_report.md`; the revised report must be the last assistant message. This is what lets the router accumulate `text_delta` chunks into the final output.
- **`draft.md` is the safety-net artifact.** If the main agent violates v2 and leaves output only as a file, the router detects the empty stream (`< 200 chars`) and surfaces `draft.md` instead, stamped `final_report_source: "file"`.

---

## 5. Shared State Channels

Every node in the graph mutates one state dict. The channels that matter:

| Channel    | Type                | Written by                  | Purpose                                     |
| :--------- | :------------------ | :-------------------------- | :------------------------------------------ |
| `messages` | `list[BaseMessage]` | All nodes                   | Conversation, tool calls, tool results      |
| `todos`    | `list[dict]`        | `write_todos`               | User-visible plan; `{content, status}`      |
| `files`    | `dict[str, str]`    | `write_file` / `edit_file`  | Virtual FS — raw dumps, `draft.md`          |
| `usage`    | `dict`              | LangChain callback          | Token accounting                            |

---

## 6. Persistence

| Mechanism       | Class              | Key                | Survives restart? | Used for                       |
| :-------------- | :----------------- | :----------------- | :---------------- | :----------------------------- |
| **Checkpointer** | `AsyncSqliteSaver` | `thread_id`        | ✅ (file on disk)  | Resume a conversation          |
| **Store**        | `InMemoryStore`    | `(namespace, key)` | ❌ (process RAM)   | Cross-thread prefs / topics    |

The checkpointer writes the full state after *every* node transition, so a follow-up `POST /research` with the same `thread_id` picks up with complete history. It's a file handle, so it lives in FastAPI's `lifespan()` — calling `get_checkpointer()` outside lifespan raises.

The store is demo-grade (in-memory, lost on restart) but fronts LangGraph's `BaseStore` interface — swap in Postgres without touching the orchestration code.
