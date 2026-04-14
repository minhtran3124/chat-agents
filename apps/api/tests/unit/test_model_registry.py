from pathlib import Path
from textwrap import dedent

import pytest

from app.models.registry import ModelRegistry, ModelSpec


@pytest.mark.unit
def test_loads_yaml_and_returns_specs(tmp_path: Path) -> None:
    yaml_path = tmp_path / "models.yaml"
    yaml_path.write_text(dedent("""
        classifier:
          provider: openai
          model: gpt-4o-mini
          temperature: 0.0
          streaming: false
        fast:
          provider: openai
          model: gpt-4o-mini
          temperature: 0.3
          streaming: true
        main:
          provider: openai
          model: gpt-4o
          temperature: 0.7
          streaming: true
    """))

    reg = ModelRegistry(yaml_path=yaml_path, env={})
    spec = reg.get("classifier")

    assert isinstance(spec, ModelSpec)
    assert spec.provider == "openai"
    assert spec.model == "gpt-4o-mini"
    assert spec.temperature == 0.0
    assert spec.streaming is False


@pytest.mark.unit
def test_env_model_overrides_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "models.yaml"
    yaml_path.write_text(dedent("""
        main:
          provider: openai
          model: gpt-4o
          temperature: 0.7
          streaming: true
    """))
    reg = ModelRegistry(yaml_path=yaml_path, env={"MAIN_MODEL": "gpt-4o-2024-11-20"})
    assert reg.get("main").model == "gpt-4o-2024-11-20"
    assert reg.get("main").provider == "openai"


@pytest.mark.unit
def test_env_provider_plus_model_swap_provider(tmp_path: Path) -> None:
    yaml_path = tmp_path / "models.yaml"
    yaml_path.write_text(dedent("""
        main:
          provider: openai
          model: gpt-4o
          temperature: 0.7
          streaming: true
    """))
    reg = ModelRegistry(
        yaml_path=yaml_path,
        env={"MAIN_PROVIDER": "anthropic", "MAIN_MODEL": "claude-sonnet-4-6"},
    )
    assert reg.get("main").provider == "anthropic"
    assert reg.get("main").model == "claude-sonnet-4-6"


@pytest.mark.unit
def test_unknown_role_raises(tmp_path: Path) -> None:
    yaml_path = tmp_path / "models.yaml"
    yaml_path.write_text(dedent("""
        main:
          provider: openai
          model: gpt-4o
    """))
    reg = ModelRegistry(yaml_path=yaml_path, env={})
    with pytest.raises(KeyError, match="Unknown model role 'missing'"):
        reg.get("missing")


@pytest.mark.unit
def test_required_providers_dedup(tmp_path: Path) -> None:
    yaml_path = tmp_path / "models.yaml"
    yaml_path.write_text(dedent("""
        classifier:
          provider: openai
          model: gpt-4o-mini
        fast:
          provider: anthropic
          model: claude-haiku-4-5
        main:
          provider: openai
          model: gpt-4o
    """))
    reg = ModelRegistry(yaml_path=yaml_path, env={})
    assert reg.required_providers() == {"openai", "anthropic"}
