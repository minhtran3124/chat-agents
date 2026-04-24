import pytest
from pydantic import ValidationError


@pytest.mark.unit
def test_anthropic_provider_with_key_resolves_default_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    from app.config.settings import Settings

    s = Settings()
    assert s.LLM_PROVIDER == "anthropic"
    assert s.LLM_MODEL == "claude-sonnet-4-6"


@pytest.mark.unit
def test_openai_provider_resolves_correct_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    from app.config.settings import Settings

    s = Settings()
    assert s.LLM_MODEL == "gpt-4o"


@pytest.mark.unit
def test_missing_provider_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import Settings

    # Pass _env_file=None so a local apps/api/.env with a real key can't
    # silently satisfy validation during tests.
    with pytest.raises(ValidationError, match="OPENAI_API_KEY is missing"):
        Settings(_env_file=None)


@pytest.mark.unit
def test_missing_tavily_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    from app.config.settings import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.unit
def test_explicit_llm_model_is_preserved(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5")

    from app.config.settings import Settings

    s = Settings()
    assert s.LLM_MODEL == "claude-haiku-4-5"


@pytest.mark.unit
def test_research_timeout_s_rejects_below_minimum(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import Settings

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, RESEARCH_TIMEOUT_S=5)
    assert "RESEARCH_TIMEOUT_S" in str(exc.value)


@pytest.mark.unit
def test_research_timeout_s_rejects_above_maximum(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import Settings

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, RESEARCH_TIMEOUT_S=7200)
    assert "RESEARCH_TIMEOUT_S" in str(exc.value)


@pytest.mark.unit
def test_research_timeout_s_default_is_500(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import Settings

    s = Settings(_env_file=None)
    assert s.RESEARCH_TIMEOUT_S == 500


@pytest.mark.unit
def test_max_tokens_per_run_default_is_200000(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import Settings

    s = Settings(_env_file=None)
    assert s.MAX_TOKENS_PER_RUN == 200_000


@pytest.mark.unit
def test_max_tokens_per_run_rejects_below_minimum(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    from app.config.settings import Settings

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, MAX_TOKENS_PER_RUN=100)
    assert "MAX_TOKENS_PER_RUN" in str(exc.value)


@pytest.mark.unit
def test_langchain_tracing_env_exported_when_set(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)

    from app.config.settings import Settings

    Settings(
        _env_file=None,
        LANGCHAIN_TRACING_V2="true",
        LANGCHAIN_API_KEY="ls__test",
        LANGCHAIN_PROJECT="chat-agents",
    )
    import os

    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    assert os.environ.get("LANGCHAIN_API_KEY") == "ls__test"
    assert os.environ.get("LANGCHAIN_PROJECT") == "chat-agents"


@pytest.mark.unit
def test_langchain_env_not_exported_when_unset(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    from app.config.settings import Settings

    Settings(_env_file=None)
    import os

    assert "LANGCHAIN_TRACING_V2" not in os.environ
    assert "LANGCHAIN_API_KEY" not in os.environ
