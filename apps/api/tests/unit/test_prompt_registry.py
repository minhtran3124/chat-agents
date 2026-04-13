# apps/api/tests/unit/test_prompt_registry.py
"""Unit tests for PromptRegistry.

Uses pytest's tmp_path fixture to create isolated on-disk prompt directories
so tests never touch the real prompts/ folder or depend on its state.
"""
from pathlib import Path

import pytest
import yaml


def _make_registry(tmp_path: Path, prompts: dict, active: dict):
    """Helper: write prompts and active.yaml to tmp_path, return a PromptRegistry."""
    from app.services.prompt_registry import PromptRegistry

    for name, versions in prompts.items():
        d = tmp_path / name
        d.mkdir()
        for version, text in versions.items():
            (d / f"{version}.md").write_text(text)

    (tmp_path / "active.yaml").write_text(yaml.dump(active))
    return PromptRegistry(prompts_dir=tmp_path)


# ── Happy path ────────────────────────────────────────────────────────────────

def test_get_returns_active_version(tmp_path):
    reg = _make_registry(
        tmp_path,
        prompts={"main": {"v1": "prompt v1", "v2": "prompt v2"}},
        active={"main": "v1"},
    )
    assert reg.get("main") == "prompt v1"


def test_get_returns_explicit_version(tmp_path):
    reg = _make_registry(
        tmp_path,
        prompts={"main": {"v1": "prompt v1", "v2": "prompt v2"}},
        active={"main": "v1"},
    )
    assert reg.get("main", version="v2") == "prompt v2"


def test_list_versions_sorted(tmp_path):
    reg = _make_registry(
        tmp_path,
        prompts={"main": {"v1": "a", "v2": "b", "v2-concise": "c"}},
        active={"main": "v1"},
    )
    assert reg.list_versions("main") == ["v1", "v2", "v2-concise"]


def test_active_versions_returns_copy(tmp_path):
    reg = _make_registry(
        tmp_path,
        prompts={"main": {"v1": "a"}, "critic": {"v1": "b"}},
        active={"main": "v1", "critic": "v1"},
    )
    av = reg.active_versions()
    assert av == {"main": "v1", "critic": "v1"}
    av["main"] = "mutated"
    assert reg.active_versions()["main"] == "v1"  # copy, not reference


# ── resolve_versions merge logic ─────────────────────────────────────────────

def test_resolve_versions_no_overrides(tmp_path):
    reg = _make_registry(
        tmp_path,
        prompts={"main": {"v1": "a"}, "researcher": {"v1": "b"}, "critic": {"v1": "c"}},
        active={"main": "v1", "researcher": "v1", "critic": "v1"},
    )
    assert reg.resolve_versions({}) == {"main": "v1", "researcher": "v1", "critic": "v1"}


def test_resolve_versions_partial_override(tmp_path):
    """Overriding only 'main' must leave researcher and critic at their active defaults."""
    reg = _make_registry(
        tmp_path,
        prompts={
            "main": {"v1": "a", "v2": "b"},
            "researcher": {"v1": "c"},
            "critic": {"v1": "d"},
        },
        active={"main": "v1", "researcher": "v1", "critic": "v1"},
    )
    resolved = reg.resolve_versions({"main": "v2"})
    assert resolved == {"main": "v2", "researcher": "v1", "critic": "v1"}


def test_resolve_versions_unknown_key_ignored(tmp_path):
    """Keys in overrides that are not known prompt names pass through silently."""
    reg = _make_registry(
        tmp_path,
        prompts={"main": {"v1": "a"}},
        active={"main": "v1"},
    )
    resolved = reg.resolve_versions({"main": "v1", "nonexistent": "v9"})
    assert "nonexistent" not in resolved


# ── Error contract ────────────────────────────────────────────────────────────

def test_get_unknown_name_raises(tmp_path):
    reg = _make_registry(
        tmp_path,
        prompts={"main": {"v1": "a"}},
        active={"main": "v1"},
    )
    with pytest.raises(KeyError, match="Unknown prompt 'critic'"):
        reg.get("critic")


def test_get_unknown_version_raises(tmp_path):
    reg = _make_registry(
        tmp_path,
        prompts={"main": {"v1": "a"}},
        active={"main": "v1"},
    )
    with pytest.raises(KeyError, match="Unknown version 'v9'"):
        reg.get("main", version="v9")


def test_list_versions_unknown_name_raises(tmp_path):
    reg = _make_registry(
        tmp_path,
        prompts={"main": {"v1": "a"}},
        active={"main": "v1"},
    )
    with pytest.raises(KeyError, match="Unknown prompt 'critic'"):
        reg.list_versions("critic")


def test_resolve_versions_bad_version_deferred_to_get(tmp_path):
    """resolve_versions returns override values without validating version strings.
    Validation is deferred to registry.get(), which raises KeyError in the router.
    This test documents the contract explicitly so it is not accidentally changed."""
    reg = _make_registry(
        tmp_path,
        prompts={"main": {"v1": "a"}},
        active={"main": "v1"},
    )
    # resolve_versions does NOT raise — it returns the bad version string
    resolved = reg.resolve_versions({"main": "v99"})
    assert resolved["main"] == "v99"
    # get() raises when the router tries to fetch the text
    with pytest.raises(KeyError, match="Unknown version 'v99'"):
        reg.get("main", version="v99")


def test_missing_active_yaml_entry_falls_back_to_v1(tmp_path):
    """A prompt present on disk but absent from active.yaml should fall back to v1."""
    from app.services.prompt_registry import PromptRegistry

    (tmp_path / "main").mkdir()
    (tmp_path / "main" / "v1.md").write_text("prompt text")
    (tmp_path / "active.yaml").write_text(yaml.dump({}))  # no entry for 'main'

    reg = PromptRegistry(prompts_dir=tmp_path)
    assert reg.get("main") == "prompt text"


def test_missing_active_yaml_file_raises(tmp_path):
    from app.services.prompt_registry import PromptRegistry

    (tmp_path / "main").mkdir()
    (tmp_path / "main" / "v1.md").write_text("text")
    # active.yaml intentionally not created

    with pytest.raises(RuntimeError, match="active.yaml not found"):
        PromptRegistry(prompts_dir=tmp_path)


def test_missing_prompts_dir_raises(tmp_path):
    from app.services.prompt_registry import PromptRegistry

    missing = tmp_path / "does_not_exist"
    with pytest.raises(RuntimeError, match="not found"):
        PromptRegistry(prompts_dir=missing)


def test_empty_md_file_raises(tmp_path):
    from app.services.prompt_registry import PromptRegistry

    (tmp_path / "main").mkdir()
    (tmp_path / "main" / "v1.md").write_text("   ")  # whitespace only
    (tmp_path / "active.yaml").write_text(yaml.dump({"main": "v1"}))

    with pytest.raises(ValueError, match="is empty"):
        PromptRegistry(prompts_dir=tmp_path)


# ── Hot-reload ────────────────────────────────────────────────────────────────

def test_reload_picks_up_new_version(tmp_path):
    reg = _make_registry(
        tmp_path,
        prompts={"main": {"v1": "original"}},
        active={"main": "v1"},
    )
    assert reg.get("main") == "original"

    # Simulate developer adding v2 and updating active.yaml
    (tmp_path / "main" / "v2.md").write_text("revised")
    (tmp_path / "active.yaml").write_text(yaml.dump({"main": "v2"}))

    reg.reload()
    assert reg.get("main") == "revised"
