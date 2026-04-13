from typing import Any

from deepagents import SubAgent, create_deep_agent

from app.services.llm_factory import get_fast_llm, get_llm
from app.services.search_tool import internet_search
from app.stores.memory_store import get_checkpointer, get_store

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


def build_research_agent() -> Any:
    main_llm = get_llm()
    fast_llm = get_fast_llm()

    subagents = [
        SubAgent(
            name="researcher",
            description=(
                "Deep-dive a single sub-topic: run searches, save raw "
                "results, return 150-word summary with citations."
            ),
            system_prompt=RESEARCHER_PROMPT,
            tools=[internet_search],
            model=fast_llm,
        ),
        SubAgent(
            name="critic",
            description=(
                "Review the draft report on virtual FS and list issues "
                "(unsupported claims, outdated info, contradictions)."
            ),
            system_prompt=CRITIC_PROMPT,
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
