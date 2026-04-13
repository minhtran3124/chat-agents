import json
import pytest


@pytest.mark.asyncio
async def test_todos_change_emits_todo_updated():
    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    chunk = {"main": {"todos": [{"text": "Step 1", "status": "pending"}]}}
    events = [ev async for ev in mapper.process("updates", chunk)]
    assert len(events) == 1
    assert events[0]["event"] == "todo_updated"
    assert json.loads(events[0]["data"])["items"][0]["text"] == "Step 1"


@pytest.mark.asyncio
async def test_same_todos_does_not_re_emit():
    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    chunk = {"main": {"todos": [{"text": "Step 1", "status": "pending"}]}}
    [ev async for ev in mapper.process("updates", chunk)]
    second = [ev async for ev in mapper.process("updates", chunk)]
    assert second == []


@pytest.mark.asyncio
async def test_new_file_in_files_dict_emits_file_saved():
    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    chunk = {"main": {"files": {"vfs://draft.md": "hello world"}}}
    events = [ev async for ev in mapper.process("updates", chunk)]
    assert len(events) == 1
    assert events[0]["event"] == "file_saved"
    payload = json.loads(events[0]["data"])
    assert payload["path"] == "vfs://draft.md"
    assert payload["preview"].startswith("hello")


@pytest.mark.asyncio
async def test_subagent_node_emits_started_then_completed():
    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    started = [
        ev async for ev in mapper.process("updates", {"researcher": {"task": "Research X"}})
    ]
    assert started[0]["event"] == "subagent_started"
    completed = [
        ev
        async for ev in mapper.process(
            "updates", {"researcher": {"summary": "found X", "__end__": True}}
        )
    ]
    assert completed[0]["event"] == "subagent_completed"


@pytest.mark.asyncio
async def test_first_chunk_with_both_task_and_summary_emits_only_started():
    """Regression: protects elif-not-if structure. A first-appearance chunk
    should always be treated as a start, even if it carries summary fields."""
    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    events = [
        ev
        async for ev in mapper.process(
            "updates",
            {"researcher": {"task": "X", "summary": "Y", "__end__": True}},
        )
    ]
    kinds = [ev["event"] for ev in events]
    assert kinds == ["subagent_started"]
    assert "subagent_completed" not in kinds


@pytest.mark.asyncio
async def test_token_drop_below_70_pct_triggers_compression():
    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    # First snapshot
    [ev async for ev in mapper.process("values", {"messages": ["x" * 10000]})]
    # Second snapshot — much smaller
    events = [ev async for ev in mapper.process("values", {"messages": ["x" * 1000]})]
    assert any(ev["event"] == "compression_triggered" for ev in events)


@pytest.mark.asyncio
async def test_text_delta_only_after_report_phase():
    from langchain_core.messages import AIMessageChunk

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()

    # Before critic completes, no text_delta
    msg = AIMessageChunk(content="hi")
    pre = [ev async for ev in mapper.process("messages", (msg, {}))]
    assert pre == []

    # Critic starts first (adds it to active subagents)
    [ev async for ev in mapper.process("updates", {"critic": {"task": "review draft"}})]
    # Critic completes → report_phase = True
    [
        ev
        async for ev in mapper.process(
            "updates", {"critic": {"summary": "ok", "__end__": True}}
        )
    ]

    # Now text_delta flows
    post = [ev async for ev in mapper.process("messages", (msg, {}))]
    assert any(ev["event"] == "text_delta" for ev in post)
