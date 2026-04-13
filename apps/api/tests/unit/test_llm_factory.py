from importlib import reload
from unittest.mock import MagicMock, patch


def _reload_with_env(monkeypatch, provider: str, key_env: str, key_val: str):
    """Reload config + factory modules so settings picks up monkeypatched env."""
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv(key_env, key_val)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    # Reload settings module first so the singleton picks up new env
    from app.config import settings as cfg_module

    reload(cfg_module)

    # Reload factory so it picks up the fresh settings singleton
    from app.services import llm_factory

    reload(llm_factory)
    return llm_factory


def test_get_llm_calls_init_chat_model_with_settings(monkeypatch):
    llm_factory = _reload_with_env(monkeypatch, "anthropic", "ANTHROPIC_API_KEY", "sk-ant-test")

    with patch("app.services.llm_factory.init_chat_model") as mock_init:
        mock_init.return_value = MagicMock()
        llm_factory.get_llm()
        mock_init.assert_called_once_with(
            model="claude-sonnet-4-6",
            model_provider="anthropic",
        )


def test_get_fast_llm_uses_haiku_for_anthropic(monkeypatch):
    llm_factory = _reload_with_env(monkeypatch, "anthropic", "ANTHROPIC_API_KEY", "sk-ant-test")

    with patch("app.services.llm_factory.init_chat_model") as mock_init:
        mock_init.return_value = MagicMock()
        llm_factory.get_fast_llm()
        mock_init.assert_called_once_with(
            model="claude-haiku-4-5",
            model_provider="anthropic",
        )


def test_get_fast_llm_uses_gpt4o_mini_for_openai(monkeypatch):
    llm_factory = _reload_with_env(monkeypatch, "openai", "OPENAI_API_KEY", "sk-test")

    with patch("app.services.llm_factory.init_chat_model") as mock_init:
        mock_init.return_value = MagicMock()
        llm_factory.get_fast_llm()
        mock_init.assert_called_once_with(
            model="gpt-4o-mini",
            model_provider="openai",
        )
