# LangChain Deep Agents — Review Notes

**Source:** *LangChain Just Released Deep Agents and It Changes How You Build AI Systems* — Towards AI (via Freedium mirror)
**Date reviewed:** 2026-04-13

---

## TL;DR

Deep Agents is LangChain's new **opinionated harness** built on top of LangGraph. It bakes in five capabilities that teams have been re-inventing individually — planning, virtual filesystem, subagent spawning, automatic context compression, and cross-conversation memory — so developers can focus on application logic instead of agent infrastructure.

> *"The same core tool-calling loop as other frameworks, but with a set of built-in capabilities baked in."*

---

## The Problem It Solves

The typical progression for teams using LangChain:

1. Start with simple **LangChain chains**.
2. Graduate to **LangGraph** when tasks need tool calling + looping.
3. Realize LangGraph is a *low-level runtime* — you have to hand-write state schemas, conditional edges, and compilation logic **before** touching the actual business problem.

Deep Agents fills this gap. It is the "opinionated defaults" layer that saves teams from re-engineering the same context management, subagent orchestration, and memory patterns over and over.

---

## Architecture — Three Layers

```
┌─────────────────────────────────┐
│  Deep Agents (harness, defaults) │   ← NEW
├─────────────────────────────────┤
│  LangGraph (runtime)            │   persistence, streaming, interrupts
├─────────────────────────────────┤
│  LangChain (building blocks)    │   models, tools, prompts
└─────────────────────────────────┘
```

---

## Five Built-in Capabilities

| # | Capability | What It Does |
|---|---|---|
| 1 | **Planning (`write_todos`)** | Agent auto-decomposes complex tasks into steps, tracks status, adapts the plan. The to-do list persists across the whole session. |
| 2 | **Virtual Filesystem** | When tool results exceed ~20,000 tokens, they're offloaded to a configurable backend; only a preview reference stays in context. Smart compression, not truncation. |
| 3 | **Subagent Spawning (`task` tool)** | Delegate isolated subtasks to specialized agents with clean contexts. Keeps the main agent's memory uncluttered. |
| 4 | **Automatic Context Compression** | At ~85% of context limit, the harness generates a structured summary replacing conversation history. Originals preserved to the filesystem. |
| 5 | **Cross-conversation Memory** | Persistent state via LangGraph Store — preferences and progress survive across threads and restarts. |

---

## Minimal Code Example

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    tools=[get_weather],
    system_prompt="You are a helpful assistant",
)
```

Research-agent example:

```python
from deepagents import create_deep_agent
from tavily import TavilyClient

agent = create_deep_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[internet_search],
    system_prompt="You are an expert researcher...",
)

result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": "Research agentic AI frameworks and write a report.",
    }]
})
```

Everything — graph construction, state, streaming, filesystem offloading, subagent spawning, compression — is handled internally.

---

## When to Use vs. When NOT to Use

**Use Deep Agents when:**
- Tasks need multi-step planning
- Tool results are large and need management
- You need long-running sessions with persistent memory
- Research automation, financial analysis, coding workflows with custom skills

**Do NOT use it when:**
- You need a simple agent → use LangChain's `create_agent`
- You need fine-grained control → use raw LangGraph

The library's own guidance: *"for simpler agents, use simpler tools."*

---

## Tradeoffs

- **Gain:** convention over configuration — teams stop re-inventing the same infrastructure.
- **Cost:** you give up granular control. The abstraction is opinionated; custom loops need raw LangGraph.

---

## Key Takeaway

Deep Agents is timely because agentic AI has matured past "can we make it call tools" into **reliable long-horizon task execution**. The industry has repeatedly built the same patterns (context offloading, subagent delegation, memory architectures) in isolation. Standardizing those patterns shifts developer focus from infrastructure back to the actual application problem.

The practical decision for any team: *do the abstraction benefits outweigh the loss of control for my use case?*

---

## Personal Notes / Questions to Explore

- How does the 20,000-token offload threshold interact with provider-specific context windows (e.g., Claude's 200k / 1M)?
- Can the virtual filesystem backend be swapped for Redis (relevant to `chat-agents` infra)?
- How does `write_todos` compare to Claude Code's task-tracking — same mental model?
- Is `create_deep_agent()` compatible with non-Anthropic providers as a first-class citizen, or Anthropic-first?
