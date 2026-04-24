from typing import Any

from langchain.chat_models import init_chat_model

from app.config.settings import settings

_FAST_MODEL = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "google": "gemini-1.5-flash",
}


def get_llm() -> Any:
    return init_chat_model(
        model=settings.LLM_MODEL,
        model_provider=settings.LLM_PROVIDER,
        streaming=True,
        max_retries=0,
    )


def get_fast_llm() -> Any:
    return init_chat_model(
        model=_FAST_MODEL[settings.LLM_PROVIDER],
        model_provider=settings.LLM_PROVIDER,
        streaming=True,
        max_retries=0,
    )
