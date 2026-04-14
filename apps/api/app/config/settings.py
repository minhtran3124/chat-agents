import os
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_MODEL = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "google": "gemini-1.5-pro",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LLM_PROVIDER: Literal["openai", "anthropic", "google"] = "openai"  # was "anthropic"
    LLM_MODEL: str | None = None

    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None

    TAVILY_API_KEY: str = Field(..., description="Required for research tool")

    CHECKPOINT_DB_PATH: str = "./data/checkpoints.sqlite"
    VFS_OFFLOAD_THRESHOLD_TOKENS: int = 20_000
    COMPRESSION_DETECTION_RATIO: float = 0.7

    LOG_LEVEL: str = "INFO"

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def _resolve_and_validate(self) -> "Settings":
        if self.LLM_MODEL is None:
            object.__setattr__(self, "LLM_MODEL", _DEFAULT_MODEL[self.LLM_PROVIDER])

        key_map = {
            "anthropic": self.ANTHROPIC_API_KEY,
            "openai": self.OPENAI_API_KEY,
            "google": self.GOOGLE_API_KEY,
        }
        if not key_map[self.LLM_PROVIDER]:
            raise ValueError(
                f"LLM_PROVIDER={self.LLM_PROVIDER} but "
                f"{self.LLM_PROVIDER.upper()}_API_KEY is missing"
            )
        # Export keys to os.environ so third-party libs (openai, anthropic, google)
        # can find them — pydantic-settings reads .env into the model but does NOT
        # set os.environ automatically.
        _env_keys = {
            "anthropic": ("ANTHROPIC_API_KEY", self.ANTHROPIC_API_KEY),
            "openai": ("OPENAI_API_KEY", self.OPENAI_API_KEY),
            "google": ("GOOGLE_API_KEY", self.GOOGLE_API_KEY),
        }
        for env_name, value in _env_keys.values():
            if value:
                os.environ.setdefault(env_name, value)
        if self.TAVILY_API_KEY:
            os.environ.setdefault("TAVILY_API_KEY", self.TAVILY_API_KEY)
        return self


settings = Settings()  # type: ignore[call-arg]  # NOTE: do not import this in unit tests — they construct fresh Settings()
