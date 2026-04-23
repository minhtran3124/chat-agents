import json


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


def test_error_default_recoverable_false():
    from app.streaming.events import error

    ev = error("boom")
    assert json.loads(ev["data"])["recoverable"] is False


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
