import json

import pytest

from app.streaming import events
from app.streaming.events import (
    ERROR_MESSAGES,
    ErrorReason,
    FinalReportSource,
)


def test_stream_start_includes_thread_id_and_iso_timestamp():
    from app.streaming.events import stream_start

    ev = stream_start("default-user")
    assert ev["event"] == "stream_start"
    payload = json.loads(ev["data"])
    assert payload["thread_id"] == "default-user"
    assert "T" in payload["started_at"]


def test_file_saved_truncates_preview():
    from app.streaming.events import file_saved

    ev = file_saved("vfs://foo.md", 1234, "x" * 1000)
    payload = json.loads(ev["data"])
    assert len(payload["preview"]) == 500
    assert payload["size_tokens"] == 1234


def test_text_delta_passes_content():
    from app.streaming.events import text_delta

    ev = text_delta("hello")
    assert ev["event"] == "text_delta"
    assert json.loads(ev["data"])["content"] == "hello"


def test_stream_end_carries_final_report_and_usage():
    from app.streaming.events import stream_end

    versions = {"main": "v1", "researcher": "v1", "critic": "v1"}
    ev = stream_end("# report", {"input_tokens": 100}, versions)
    p = json.loads(ev["data"])
    assert p["final_report"] == "# report"
    assert p["usage"] == {"input_tokens": 100}
    assert p["versions_used"] == versions
    assert p["final_report_source"] == "stream"


def test_stream_end_final_report_source_file():
    from app.streaming.events import stream_end

    versions = {"main": "v2", "researcher": "v1", "critic": "v1"}
    ev = stream_end("# report", {}, versions, final_report_source="file")
    p = json.loads(ev["data"])
    assert p["final_report_source"] == "file"


def test_compression_triggered_default_not_synthetic():
    from app.streaming.events import compression_triggered

    ev = compression_triggered(10000, 5000)
    p = json.loads(ev["data"])
    assert p["original_tokens"] == 10000
    assert p["compressed_tokens"] == 5000
    assert p["synthetic"] is False


def test_compression_triggered_synthetic_flag_passes_through():
    from app.streaming.events import compression_triggered

    ev = compression_triggered(40000, 20000, synthetic=True)
    p = json.loads(ev["data"])
    assert p["synthetic"] is True


def test_reflection_logged_carries_role_and_text():
    from app.streaming.events import reflection_logged

    ev = reflection_logged("researcher", "need primary source on X")
    assert ev["event"] == "reflection_logged"
    p = json.loads(ev["data"])
    assert p["role"] == "researcher"
    assert p["reflection"] == "need primary source on X"


def test_reflection_logged_truncates_at_2000_chars():
    from app.streaming.events import reflection_logged

    ev = reflection_logged("main", "x" * 5000)
    p = json.loads(ev["data"])
    assert len(p["reflection"]) == 2000


# ---------------------------------------------------------------------------
# Task 1.2 — ErrorReason, FinalReportSource, ERROR_MESSAGES
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_error_messages_catalog_covers_both_reasons():
    assert set(ERROR_MESSAGES.keys()) == {"timeout", "internal", "rate_limited"}
    for _reason, message in ERROR_MESSAGES.items():
        assert isinstance(message, str)
        assert len(message) > 10  # non-empty, human-readable


@pytest.mark.unit
def test_error_reason_type_alias_values():
    from typing import get_args

    assert set(get_args(ErrorReason)) == {"timeout", "internal", "rate_limited"}


@pytest.mark.unit
def test_final_report_source_widened_to_include_error():
    from typing import get_args

    assert set(get_args(FinalReportSource)) == {"stream", "file", "error"}


# ---------------------------------------------------------------------------
# Task 1.3 — refactored error() factory
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_error_factory_timeout_shape():
    ev = events.error("timeout")
    assert ev["event"] == "error"
    data = json.loads(ev["data"])
    assert data["reason"] == "timeout"
    assert data["recoverable"] is True
    assert data["message"] == ERROR_MESSAGES["timeout"]


@pytest.mark.unit
def test_error_factory_internal_shape():
    ev = events.error("internal")
    assert ev["event"] == "error"
    data = json.loads(ev["data"])
    assert data["reason"] == "internal"
    assert data["recoverable"] is False
    assert data["message"] == ERROR_MESSAGES["internal"]


# ---------------------------------------------------------------------------
# Task 1.4 — widen stream_end() final_report_source
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_stream_end_accepts_error_as_final_report_source():
    ev = events.stream_end(
        final_report="",
        usage={},
        versions_used={"main": "v3"},
        final_report_source="error",
    )
    assert ev["event"] == "stream_end"
    data = json.loads(ev["data"])
    assert data["final_report_source"] == "error"
    assert data["final_report"] == ""


@pytest.mark.unit
def test_budget_exceeded_factory_shape():
    from app.streaming.events import budget_exceeded

    ev = budget_exceeded(tokens_used=207_432, limit=200_000)
    assert ev["event"] == "budget_exceeded"
    data = json.loads(ev["data"])
    assert data["tokens_used"] == 207_432
    assert data["limit"] == 200_000
    assert "207,432" in data["message"]
    assert "200,000" in data["message"]
