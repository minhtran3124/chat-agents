import pytest
from pydantic import ValidationError


def test_anthropic_provider_with_key_resolves_default_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    from app.config.settings import Settings

    s = Settings()
    assert s.LLM_PROVIDER == "anthropic"
    assert s.LLM_MODEL == "claude-sonnet-4-6"


def test_openai_provider_resolves_correct_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    from app.config.settings import Settings

    s = Settings()
    assert s.LLM_MODEL == "gpt-4o"


def test_missing_provider_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import Settings

    # Pass _env_file=None so a local apps/api/.env with a real key can't
    # silently satisfy validation during tests.
    with pytest.raises(ValidationError, match="OPENAI_API_KEY is missing"):
        Settings(_env_file=None)


def test_missing_tavily_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    from app.config.settings import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_explicit_llm_model_is_preserved(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5")

    from app.config.settings import Settings

    s = Settings()
    assert s.LLM_MODEL == "claude-haiku-4-5"
