import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel


class ModelSpec(BaseModel):
    provider: Literal["openai", "anthropic", "google"]
    model: str
    temperature: float = 0.7
    streaming: bool = True
    response_format: str | None = None

    model_config = {"frozen": True}


class ModelRegistry:
    def __init__(self, yaml_path: Path, env: Mapping[str, str] | None = None) -> None:
        self._yaml_path = yaml_path
        self._env = dict(env if env is not None else os.environ)
        self._specs: dict[str, ModelSpec] = {}
        self._clients: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        if not self._yaml_path.exists():
            raise RuntimeError(f"models.yaml not found: {self._yaml_path}")
        with self._yaml_path.open() as f:
            raw = yaml.safe_load(f) or {}

        specs: dict[str, ModelSpec] = {}
        for role, block in raw.items():
            merged = dict(block)
            env_model = self._env.get(f"{role.upper()}_MODEL")
            env_provider = self._env.get(f"{role.upper()}_PROVIDER")
            if env_model:
                merged["model"] = env_model
            if env_provider:
                merged["provider"] = env_provider
            specs[role] = ModelSpec(**merged)

        self._specs = specs
        self._clients.clear()

    def get(self, role: str) -> ModelSpec:
        if role not in self._specs:
            raise KeyError(f"Unknown model role '{role}'. Available: {sorted(self._specs)}")
        return self._specs[role]

    def build(self, role: str) -> Any:
        if role in self._clients:
            return self._clients[role]
        from langchain.chat_models import init_chat_model

        spec = self.get(role)
        kwargs: dict[str, Any] = {
            "model": spec.model,
            "model_provider": spec.provider,
            "temperature": spec.temperature,
            "streaming": spec.streaming,
        }
        client = init_chat_model(**kwargs)
        self._clients[role] = client
        return client

    def roles(self) -> list[str]:
        return sorted(self._specs)

    def required_providers(self) -> set[str]:
        return {s.provider for s in self._specs.values()}
