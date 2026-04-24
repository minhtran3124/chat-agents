from types import SimpleNamespace

import pytest


@pytest.mark.unit
def test_extract_token_count_from_usage_metadata():
    from app.routers.research import _extract_token_count

    msg = SimpleNamespace(usage_metadata={"input_tokens": 100, "output_tokens": 50})
    assert _extract_token_count(msg) == 150


@pytest.mark.unit
def test_extract_token_count_missing_metadata():
    from app.routers.research import _extract_token_count

    msg = SimpleNamespace()  # no usage_metadata attribute
    assert _extract_token_count(msg) == 0


@pytest.mark.unit
def test_extract_token_count_metadata_none():
    from app.routers.research import _extract_token_count

    msg = SimpleNamespace(usage_metadata=None)
    assert _extract_token_count(msg) == 0


@pytest.mark.unit
def test_extract_token_count_partial_metadata():
    """Only input_tokens set — output_tokens defaults to 0."""
    from app.routers.research import _extract_token_count

    msg = SimpleNamespace(usage_metadata={"input_tokens": 42})
    assert _extract_token_count(msg) == 42
