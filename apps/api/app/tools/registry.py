from collections.abc import Callable
from typing import TypeVar

from langchain_core.tools import BaseTool

T = TypeVar("T", bound=BaseTool)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, name: str) -> Callable[[T], T]:
        def decorator(tool_obj: T) -> T:
            if name in self._tools:
                raise RuntimeError(f"Tool '{name}' already registered")
            self._tools[name] = tool_obj
            return tool_obj

        return decorator

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool '{name}'. Available: {sorted(self._tools)}")
        return self._tools[name]

    def get_many(self, names: list[str]) -> list[BaseTool]:
        return [self.get(n) for n in names]

    def names(self) -> list[str]:
        return sorted(self._tools)


# Module-level singleton. Use this in application code.
# Tests should construct their own ToolRegistry() instance.
registry = ToolRegistry()
register_tool = registry.register
