# Claude Code Agent Teams — Master Reference Guide

> Authoritative reference for designing, spawning, and operating multi-agent teams in Claude Code.
> Source: https://code.claude.com/docs/en/agent-teams
> Last fetched: 2026-04-14
> Applies to: Claude Code v2.1.32 or later (check with `claude --version`)

Use this guide when planning agent teams for any codebase. It captures what the official docs say, plus practical patterns for choosing between subagents and teams, sizing teams, and avoiding the sharp edges.

---

## 1. What an Agent Team Is (and Isn't)

An **agent team** is a group of independent Claude Code sessions that coordinate on a shared task list and message each other directly. One session is the **lead** (the session that created the team). The others are **teammates**, each with its own context window, permissions, tools, and terminal presence.

Key differences vs. a normal session or a subagent:

| Aspect            | Single session        | Subagents                              | Agent team                                          |
| :---------------- | :-------------------- | :------------------------------------- | :-------------------------------------------------- |
| Context window    | One shared            | Each sub has its own; result summarized back to main | Each teammate has its own; fully independent        |
| Communication     | N/A                   | Sub → main only                        | Any teammate ↔ any teammate, direct                 |
| Coordination      | User drives           | Main agent dispatches and collects     | Shared task list + self-claim, teammates self-coordinate |
| Best for          | Sequential work       | Focused lookups and verifications      | Parallel work that requires discussion or challenge |
| Token cost        | Lowest                | Low–medium (result summarized)         | High (each teammate is a full Claude session)       |

> **Rule of thumb.** If workers only need to *report back*, use subagents. If workers need to *talk to each other*, use a team.

---

## 2. Enabling Agent Teams

Agent teams are **experimental** and disabled by default.

Enable via `settings.json` (or your shell environment):

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

Requirements:
- Claude Code **v2.1.32 or later**
- For split-pane display: **tmux** (macOS/Linux) or **iTerm2 with the `it2` CLI** + Python API enabled

Check version:

```bash
claude --version
```

---

## 3. Starting a Team

Once enabled, start a team by describing the job and team shape in natural language. Claude spawns teammates and coordinates from there.

Example prompt that works well (three independent perspectives, no file conflicts):

```text
I'm designing a CLI tool that helps developers track TODO comments across
their codebase. Create an agent team to explore this from different angles: one
teammate on UX, one on technical architecture, one playing devil's advocate.
```

Claude can also **propose** a team when it thinks parallel work would help. You always confirm before it spawns.

---

## 4. Team Architecture

| Component     | Role                                                                                       |
| :------------ | :----------------------------------------------------------------------------------------- |
| **Team lead** | The main Claude Code session — creates the team, spawns teammates, coordinates, cleans up |
| **Teammates** | Independent Claude Code instances, each with its own context window                        |
| **Task list** | Shared work-item list teammates claim and complete (file-locked to avoid races)            |
| **Mailbox**   | Messaging system: direct messages or broadcasts between agents                             |

Storage locations (managed automatically — **do not hand-edit**):

- Team config: `~/.claude/teams/{team-name}/config.json`
- Task list: `~/.claude/tasks/{team-name}/`

Project-level team config (e.g. `.claude/teams/teams.json`) is **not recognized** — Claude treats it as an ordinary file.

Task states: `pending`, `in progress`, `completed`. Tasks can declare dependencies; blocked tasks unblock automatically when their prerequisites complete.

---

## 5. Spawning and Configuring Teammates

### 5.1 Specify team size and model

```text
Create a team with 4 teammates to refactor these modules in parallel.
Use Sonnet for each teammate.
```

### 5.2 Use subagent definitions as teammate roles

You can reference any subagent type (project, user, plugin, or CLI-defined) as a teammate's role:

```text
Spawn a teammate using the security-reviewer agent type to audit the auth module.
```

What carries over from the subagent definition:
- `tools` allowlist (enforced)
- `model` (applied)
- Definition body → **appended** to the teammate's system prompt (does not replace it)

What does **not** carry over:
- `skills` and `mcpServers` frontmatter fields — teammates load skills/MCP servers from project + user settings like a regular session

**Always available** to every teammate even if `tools` restricts others: `SendMessage`, task management tools.

### 5.3 Require plan approval before implementation

For risky work, make teammates plan first:

```text
Spawn an architect teammate to refactor the authentication module.
Require plan approval before they make any changes.
```

Flow: teammate plans in read-only mode → submits plan → lead approves or rejects with feedback → on reject, teammate revises and resubmits → on approve, teammate exits plan mode and implements.

The lead decides autonomously. Steer it with criteria in your prompt, e.g.:

```text
Only approve plans that include test coverage. Reject plans that modify the database schema.
```

### 5.4 Naming teammates

The lead assigns names at spawn. To get predictable names you can reference later, tell the lead what to call each teammate in the spawn prompt.

---

## 6. Interacting With the Team

### 6.1 Display modes

| Mode           | Where teammates appear                            | Setup                               |
| :------------- | :------------------------------------------------ | :---------------------------------- |
| `in-process`   | Inside the main terminal; cycle with **Shift+Down** | None — works in any terminal       |
| `tmux` / split | Each teammate in its own pane                     | Requires tmux or iTerm2 + `it2` CLI |
| `auto` *(default)* | Split panes if already inside tmux, otherwise in-process | —                          |

Global default — edit `~/.claude.json`:

```json
{
  "teammateMode": "in-process"
}
```

One-off override per session:

```bash
claude --teammate-mode in-process
```

Keyboard controls in in-process mode:
- **Shift+Down**: cycle through teammates; wraps back to lead
- **Enter**: view a teammate's session
- **Escape**: interrupt the current turn
- **Ctrl+T**: toggle the task list

### 6.2 Talking to a specific teammate

Each teammate is a full independent session, so you can message any of them directly:
- **In-process**: Shift+Down to the teammate, type, send
- **Split panes**: click into the pane and interact normally

### 6.3 Assigning tasks

Two models, both supported:
- **Lead assigns**: tell the lead which task goes to which teammate
- **Self-claim**: when a teammate finishes, it picks the next unassigned, unblocked task itself

File-locked task claiming prevents two teammates from grabbing the same task.

### 6.4 Shutting down a teammate

```text
Ask the researcher teammate to shut down
```

Teammate can approve (exits gracefully) or reject with an explanation.

### 6.5 Cleaning up the team

```text
Clean up the team
```

> **Always let the lead run cleanup.** Teammates may not resolve team context correctly and can leave resources inconsistent. Shut down active teammates before cleanup — it fails if any are still running.

---

## 7. Context, Communication, and Messaging

Each teammate, when spawned, loads:
- `CLAUDE.md` (from its working directory)
- MCP servers
- Skills
- The **spawn prompt** from the lead

It does **not** inherit the lead's conversation history. Always include task-specific context in the spawn prompt.

Runtime messaging primitives:
- **`message`** — send to one teammate by name
- **`broadcast`** — send to all teammates at once (**use sparingly** — cost scales with team size)
- **Automatic delivery** — messages arrive without the lead polling
- **Idle notifications** — when a teammate finishes and stops, the lead is notified automatically
- **Shared task list** — any agent can read status and claim available work

Teams can also read the team config file to discover members (the `members` array contains name, agent ID, and agent type).

---

## 8. Permissions

- Teammates inherit the **lead's permission mode** at spawn time
- If the lead runs with `--dangerously-skip-permissions`, so do all teammates
- You **can** change individual teammate modes after spawn
- You **cannot** set per-teammate modes at spawn time
- Permission prompts from teammates bubble up to the lead — pre-approve common operations to cut interruptions

---

## 9. Quality Gates via Hooks

Use hooks to enforce rules at team lifecycle events. Exit code `2` sends feedback and blocks/continues the action:

| Hook             | Fires when                              | Exit 2 effect                              |
| :--------------- | :-------------------------------------- | :----------------------------------------- |
| `TeammateIdle`   | A teammate is about to go idle          | Keeps teammate working, sends feedback     |
| `TaskCreated`    | A task is being created                 | Prevents creation, sends feedback          |
| `TaskCompleted` | A task is being marked complete         | Prevents completion, sends feedback        |

Useful patterns: require tests pass before `TaskCompleted`, require a spec link before `TaskCreated`, nudge a stuck teammate in `TeammateIdle`.

---

## 10. When to Use an Agent Team

### Strong fits
- **Research and review** — multiple angles on one problem, with cross-critique
- **New modules or features** — each teammate owns a distinct piece
- **Debugging with competing hypotheses** — parallel theory testing beats sequential anchoring
- **Cross-layer coordination** — frontend, backend, and tests owned separately

### Weak fits (prefer single session or subagents)
- Sequential work where each step depends on the previous
- Multiple edits to the same file
- Dense webs of dependencies
- Routine tasks where coordination overhead > parallel benefit

---

## 11. Canonical Use Case Examples

### Parallel code review

```text
Create an agent team to review PR #142. Spawn three reviewers:
- One focused on security implications
- One checking performance impact
- One validating test coverage
Have them each review and report findings.
```

Why it works: three non-overlapping lenses, no shared files written, lead synthesizes at the end.

### Investigation with competing hypotheses

```text
Users report the app exits after one message instead of staying connected.
Spawn 5 agent teammates to investigate different hypotheses. Have them talk to
each other to try to disprove each other's theories, like a scientific
debate. Update the findings doc with whatever consensus emerges.
```

Why it works: adversarial structure defeats anchoring bias — a theory that survives five skeptics is much more likely to be the root cause than one a single agent stops on.

---

## 12. Best Practices

### Give teammates enough context
Teammates get `CLAUDE.md`, MCP, skills — but **not** the lead's history. Put task-specific detail in the spawn prompt:

```text
Spawn a security reviewer teammate with the prompt: "Review the authentication module
at src/auth/ for security vulnerabilities. Focus on token handling, session
management, and input validation. The app uses JWT tokens stored in
httpOnly cookies. Report any issues with severity ratings."
```

### Size the team right
- Default: **3–5 teammates**
- Target: **5–6 tasks per teammate** — keeps everyone productive without excessive switching
- Scale up only when work genuinely parallelizes
- Three focused teammates usually beat five scattered ones

### Size tasks right
- Too small → coordination overhead eats the benefit
- Too large → teammates drift for too long before check-in
- Ideal → self-contained unit with a clear deliverable (function, test file, review)

### Keep the lead from doing the work itself
If the lead starts implementing instead of waiting, say:

```text
Wait for your teammates to complete their tasks before proceeding
```

### Start with research and review
First-time team? Pick a task with clear boundaries and no code changes: PR review, library research, bug investigation. You get the value of parallelism without the coordination tax of parallel writes.

### Avoid file conflicts
Two teammates writing the same file → overwrites. Slice the work so each teammate owns a distinct file set.

### Monitor and steer
Check progress, redirect bad approaches, synthesize findings as they arrive. A team running unattended is a team wasting tokens.

---

## 13. Troubleshooting

| Symptom                                      | Likely cause and fix                                                                                           |
| :------------------------------------------- | :------------------------------------------------------------------------------------------------------------- |
| No teammates visible                         | In-process: press **Shift+Down** to cycle. Also check the task was complex enough for Claude to spawn a team. |
| Split panes not working                      | Run `which tmux`; for iTerm2 install `it2` CLI and enable Python API in Settings → General → Magic.           |
| Too many permission prompts                  | Pre-approve common operations in [permission settings](https://code.claude.com/docs/en/permissions).           |
| Teammate stopped after an error              | Message it directly with more context, or spawn a replacement teammate to continue.                            |
| Lead shuts down before work is done          | Tell it to keep going; also tell it to wait for teammates rather than do the work itself.                      |
| Orphaned tmux session after cleanup          | `tmux ls` then `tmux kill-session -t <session-name>`.                                                          |

---

## 14. Known Limitations (as of the linked docs)

- **No session resumption for in-process teammates** — `/resume` and `/rewind` do not restore them; the lead may try to message ghosts. Spawn replacements.
- **Task status can lag** — teammates occasionally fail to mark complete, blocking dependents. Update manually or nudge the teammate.
- **Shutdown can be slow** — teammates finish their current tool call first.
- **One team per session** — clean up the current team before starting a new one.
- **No nested teams** — teammates cannot spawn their own teams; only the lead can.
- **Lead is fixed** — the session that creates the team leads it for its lifetime. No promotion, no transfer.
- **Permissions fixed at spawn** — you can adjust individual modes later, but not at spawn.
- **Split panes** — not supported in VS Code's integrated terminal, Windows Terminal, or Ghostty. Use in-process mode there.

---

## 15. Checklist — Before Spawning a Team

- [ ] Task genuinely benefits from parallel workers who need to talk (else use subagents)
- [ ] Agent teams enabled (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)
- [ ] Claude Code ≥ v2.1.32
- [ ] 3–5 teammates planned, 5–6 tasks per teammate
- [ ] Each teammate owns a **distinct** set of files/concerns
- [ ] Spawn prompts include task-specific context (teammates don't inherit history)
- [ ] Reusable roles mapped to subagent definitions where applicable
- [ ] Risky work gated by plan approval
- [ ] `TaskCompleted` / `TaskCreated` / `TeammateIdle` hooks configured if quality gates matter
- [ ] Display mode confirmed (tmux/iTerm2 present if using split panes)
- [ ] Cleanup plan: shut down teammates, then ask the lead to clean up the team

---

## 16. Related Approaches

- **[Subagents](https://code.claude.com/docs/en/sub-agents)** — lighter, one-shot delegation; sub reports to main only
- **[Git worktrees](https://code.claude.com/docs/en/common-workflows#run-parallel-claude-code-sessions-with-git-worktrees)** — manually run multiple independent Claude Code sessions in isolated trees
- **[Feature comparison](https://code.claude.com/docs/en/features-overview#compare-similar-features)** — side-by-side table of subagents vs agent teams

---

## 17. Quick Reference — Commands and Settings

```bash
# Version check
claude --version

# Force in-process mode for one session
claude --teammate-mode in-process

# Kill an orphaned tmux session
tmux ls
tmux kill-session -t <session-name>
```

```json
// settings.json — enable agent teams
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

```json
// ~/.claude.json — set default display mode
{
  "teammateMode": "in-process"
}
```

Common natural-language prompts:

```text
# Spawn a sized team with a specific model
Create a team with 4 teammates to refactor these modules in parallel. Use Sonnet for each teammate.

# Spawn a named, role-based teammate
Spawn a teammate using the security-reviewer agent type to audit the auth module. Call it "sec".

# Require plan approval
Require plan approval before any teammate makes changes. Only approve plans that include test coverage.

# Keep the lead from working
Wait for your teammates to complete their tasks before proceeding.

# Shut down
Ask the researcher teammate to shut down.

# Clean up
Clean up the team.
```
