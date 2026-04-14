from typing import Any

from deepagents import SubAgent, create_deep_agent

from app.agents.specs import AgentSpec


def build_deep_research_agent(
    spec: AgentSpec,
    model_registry: Any,
    tool_registry: Any,
    prompt_registry: Any,
    checkpointer: Any,
    store: Any,
    prompt_versions: dict[str, str] | None = None,
) -> Any:
    versions = prompt_versions or {}
    main_llm = model_registry.build(spec.model_role)

    sub_specs: list[SubAgent] = []
    for sub in spec.subagents:
        sub_specs.append(
            SubAgent(
                name=sub.name,
                description=_description_for(sub.name),
                system_prompt=prompt_registry.get(sub.prompt_name, version=versions.get(sub.prompt_name)),
                tools=tool_registry.get_many(sub.tools),
                model=model_registry.build(sub.model_role),
            )
        )

    return create_deep_agent(
        model=main_llm,
        tools=tool_registry.get_many(spec.tools),
        subagents=sub_specs,
        system_prompt=prompt_registry.get(spec.prompt_name, version=versions.get(spec.prompt_name)),
        store=store,
        checkpointer=checkpointer,
    )


def _description_for(name: str) -> str:
    return {
        "researcher": (
            "Deep-dive a single sub-topic: run searches, save raw results, "
            "return 150-word summary with citations."
        ),
        "critic": (
            "Review the draft report and list issues (unsupported claims, "
            "outdated info, contradictions)."
        ),
    }.get(name, name)
