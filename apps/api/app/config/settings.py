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

    LLM_PROVIDER: Literal["anthropic", "openai", "google"] = "anthropic"
    LLM_MODEL: str | None = None

    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None

    TAVILY_API_KEY: str = Field(..., description="Required for research tool")

    CHECKPOINT_DB_PATH: str = "./data/checkpoints.sqlite"
    VFS_OFFLOAD_THRESHOLD_TOKENS: int = 20_000
    COMPRESSION_DETECTION_RATIO: float = 0.7

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
        return self


settings = Settings()  # NOTE: do not import this in unit tests — they construct fresh Settings()
