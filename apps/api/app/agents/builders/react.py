from typing import Any, Protocol

from langgraph.prebuilt import create_react_agent

from app.agents.specs import AgentSpec


class _PromptRegistryProto(Protocol):
    def get(self, name: str, version: str | None = None) -> str: ...


def build_react_agent(
    spec: AgentSpec,
    model_registry: Any,
    tool_registry: Any,
    prompt_registry: _PromptRegistryProto,
    prompt_version: str | None = None,
) -> Any:
    model = model_registry.build(spec.model_role)
    tools = tool_registry.get_many(spec.tools)
    prompt = prompt_registry.get(spec.prompt_name, version=prompt_version)
    return create_react_agent(
        model=model,
        tools=tools,
        prompt=prompt,
        name=spec.name,
    )
