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
async def test_task_tool_call_emits_subagent_started():
    """deepagents invokes subagents via a `task` tool — detection happens on
    AIMessage.tool_calls, not on a LangGraph node named after the subagent."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "id": "call_abc",
                "args": {"subagent_type": "researcher", "description": "Research X"},
            }
        ],
    )
    events = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    assert len(events) == 1
    assert events[0]["event"] == "subagent_started"
    payload = json.loads(events[0]["data"])
    assert payload == {"id": "call_abc", "name": "researcher", "task": "Research X"}


@pytest.mark.asyncio
async def test_task_tool_response_emits_subagent_completed():
    from langchain_core.messages import AIMessage, ToolMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "id": "call_abc",
                "args": {"subagent_type": "researcher", "description": "Research X"},
            }
        ],
    )
    [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]

    tool_msg = ToolMessage(content="found X", tool_call_id="call_abc", name="task")
    events = [ev async for ev in mapper.process("updates", {"tools": {"messages": [tool_msg]}})]
    assert len(events) == 1
    assert events[0]["event"] == "subagent_completed"
    payload = json.loads(events[0]["data"])
    assert payload == {"id": "call_abc", "summary": "found X"}


@pytest.mark.asyncio
async def test_non_task_tool_calls_ignored():
    """Only `task` tool calls should produce subagent events — other tools
    (e.g. internet_search, write_todos) must not."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "internet_search", "id": "call_xyz", "args": {"query": "foo"}}],
    )
    events = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    assert events == []


@pytest.mark.asyncio
async def test_parallel_task_calls_tracked_separately():
    """Two concurrent task calls must emit independent started/completed pairs
    keyed by tool_call_id."""
    from langchain_core.messages import AIMessage, ToolMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "id": "call_1",
                "args": {"subagent_type": "researcher", "description": "topic A"},
            },
            {
                "name": "task",
                "id": "call_2",
                "args": {"subagent_type": "critic", "description": "review draft"},
            },
        ],
    )
    starts = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    assert [ev["event"] for ev in starts] == ["subagent_started", "subagent_started"]
    start_ids = {json.loads(ev["data"])["id"] for ev in starts}
    assert start_ids == {"call_1", "call_2"}

    # Completions arrive in reverse order — both must be recognized.
    tool_2 = ToolMessage(content="critique OK", tool_call_id="call_2", name="task")
    tool_1 = ToolMessage(content="research OK", tool_call_id="call_1", name="task")
    done = [ev async for ev in mapper.process("updates", {"tools": {"messages": [tool_2, tool_1]}})]
    assert [ev["event"] for ev in done] == ["subagent_completed", "subagent_completed"]
    done_ids = [json.loads(ev["data"])["id"] for ev in done]
    assert done_ids == ["call_2", "call_1"]


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
async def test_overwrite_wrapped_messages_does_not_crash():
    """Regression: LangGraph Overwrite channel wrapper on 'messages' field.
    update.get('messages') returns Overwrite(value=[...]) not a bare list —
    iterating it directly raises TypeError: 'Overwrite' object is not iterable."""
    from app.streaming.chunk_mapper import ChunkMapper

    class FakeOverwrite:
        """Minimal stand-in for langgraph's Overwrite channel type."""

        def __init__(self, value: list) -> None:
            self.value = value

    mapper = ChunkMapper()
    chunk = {"main": {"messages": FakeOverwrite(value=[])}}
    # Must not raise, must produce no events (empty message list)
    evts = [ev async for ev in mapper.process("updates", chunk)]
    assert evts == []


@pytest.mark.asyncio
async def test_non_string_file_content_does_not_crash():
    """Regression: deepagents may store file payloads as dicts/lists.
    tiktoken.encode() throws 'expected string or buffer' on non-strings —
    the mapper must coerce instead of propagating the TypeError."""
    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    chunk = {"main": {"files": {"vfs://draft.md": {"content": "hi", "v": 1}}}}
    events = [ev async for ev in mapper.process("updates", chunk)]
    assert len(events) == 1
    assert events[0]["event"] == "file_saved"


@pytest.mark.asyncio
async def test_text_delta_always_emitted():
    from langchain_core.messages import AIMessageChunk

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()

    # text_delta is emitted immediately — no phase gate
    msg = AIMessageChunk(content="hi")
    evts = [ev async for ev in mapper.process("messages", (msg, {}))]
    assert any(ev["event"] == "text_delta" for ev in evts)


@pytest.mark.asyncio
async def test_think_tool_call_emits_reflection_logged_as_main_by_default():
    """Without an active task subagent, think_tool reflections belong to the main agent."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "think_tool",
                "id": "call_r1",
                "args": {"reflection": "need a primary source on X"},
            }
        ],
    )
    events = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    reflection_events = [ev for ev in events if ev["event"] == "reflection_logged"]
    assert len(reflection_events) == 1
    payload = json.loads(reflection_events[0]["data"])
    assert payload == {"role": "main", "reflection": "need a primary source on X"}


@pytest.mark.asyncio
async def test_think_tool_call_emits_as_researcher_while_task_in_flight():
    """After a task (subagent) is spawned, further think_tool calls are attributed
    to the researcher until the task completes."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    task_ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "id": "call_task_1",
                "args": {"subagent_type": "researcher", "description": "topic A"},
            }
        ],
    )
    [ev async for ev in mapper.process("updates", {"model": {"messages": [task_ai]}})]

    think_ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "think_tool",
                "id": "call_r2",
                "args": {"reflection": "first search closed the gap"},
            }
        ],
    )
    events = [ev async for ev in mapper.process("updates", {"tools": {"messages": [think_ai]}})]
    reflection_events = [ev for ev in events if ev["event"] == "reflection_logged"]
    assert len(reflection_events) == 1
    payload = json.loads(reflection_events[0]["data"])
    assert payload["role"] == "researcher"


@pytest.mark.asyncio
async def test_think_tool_call_dedupes_by_tool_call_id():
    """Same tool_call_id seen across chunk rebroadcasts must emit once."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "think_tool",
                "id": "call_dupe",
                "args": {"reflection": "same reflection"},
            }
        ],
    )
    first = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    second = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    assert len([ev for ev in first if ev["event"] == "reflection_logged"]) == 1
    assert len([ev for ev in second if ev["event"] == "reflection_logged"]) == 0


@pytest.mark.asyncio
async def test_think_tool_with_empty_reflection_is_ignored():
    """A malformed think_tool call (missing/empty reflection) must not emit."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "think_tool",
                "id": "call_empty",
                "args": {"reflection": ""},
            }
        ],
    )
    events = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    assert all(ev["event"] != "reflection_logged" for ev in events)


@pytest.mark.asyncio
async def test_internet_search_tool_call_does_not_emit_reflection():
    """Only think_tool produces reflection_logged — other tools must not."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "internet_search",
                "id": "call_search",
                "args": {"query": "deep research"},
            }
        ],
    )
    events = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    assert all(ev["event"] != "reflection_logged" for ev in events)
