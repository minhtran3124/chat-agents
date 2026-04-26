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
    started = [ev for ev in events if ev["event"] == "subagent_started"]
    assert len(started) == 1
    payload = json.loads(started[0]["data"])
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
    completed = [ev for ev in events if ev["event"] == "subagent_completed"]
    assert len(completed) == 1
    payload = json.loads(completed[0]["data"])
    assert payload == {"id": "call_abc", "summary": "found X"}


@pytest.mark.asyncio
async def test_non_task_tool_calls_do_not_emit_subagent_events():
    """Only `task` tool calls produce subagent_started/completed — other tools
    (e.g. internet_search, write_todos) must not, even though they do emit the
    generic tool_call_started event."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "internet_search", "id": "call_xyz", "args": {"query": "foo"}}],
    )
    events = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    assert all(ev["event"] not in ("subagent_started", "subagent_completed") for ev in events)


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
    raw_starts = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    starts = [ev for ev in raw_starts if ev["event"] == "subagent_started"]
    assert [ev["event"] for ev in starts] == ["subagent_started", "subagent_started"]
    start_ids = {json.loads(ev["data"])["id"] for ev in starts}
    assert start_ids == {"call_1", "call_2"}

    # Completions arrive in reverse order — both must be recognized.
    tool_2 = ToolMessage(content="critique OK", tool_call_id="call_2", name="task")
    tool_1 = ToolMessage(content="research OK", tool_call_id="call_1", name="task")
    raw_done = [
        ev async for ev in mapper.process("updates", {"tools": {"messages": [tool_2, tool_1]}})
    ]
    done = [ev for ev in raw_done if ev["event"] == "subagent_completed"]
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


@pytest.mark.asyncio
async def test_tool_call_started_emitted_for_every_tool():
    """Every tool_call (task, think_tool, internet_search, …) must emit tool_call_started."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "internet_search", "id": "call_a", "args": {"query": "X"}},
            {"name": "read_file", "id": "call_b", "args": {"file_path": "/r/searches/x.md"}},
        ],
    )
    events = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    starts = [ev for ev in events if ev["event"] == "tool_call_started"]
    assert len(starts) == 2
    payload_a = json.loads(starts[0]["data"])
    assert payload_a == {
        "id": "call_a",
        "role": "main",
        "tool_name": "internet_search",
        "args_preview": '{"query": "X"}',
    }
    payload_b = json.loads(starts[1]["data"])
    assert payload_b["tool_name"] == "read_file"
    assert payload_b["role"] == "main"


@pytest.mark.asyncio
async def test_tool_call_started_role_reflects_active_subagent():
    """While a researcher task is in flight, child tool_calls are tagged researcher."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    task_ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "id": "call_task_1",
                "args": {"subagent_type": "researcher", "description": "topic"},
            }
        ],
    )
    [ev async for ev in mapper.process("updates", {"model": {"messages": [task_ai]}})]

    child_ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "internet_search", "id": "call_child", "args": {"query": "Y"}},
        ],
    )
    events = [ev async for ev in mapper.process("updates", {"tools": {"messages": [child_ai]}})]
    starts = [ev for ev in events if ev["event"] == "tool_call_started"]
    payload = json.loads(starts[0]["data"])
    assert payload["role"] == "researcher"


@pytest.mark.asyncio
async def test_tool_call_started_role_critic_when_critic_active():
    """Role attribution distinguishes critic from researcher."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    task_ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "id": "call_critic",
                "args": {"subagent_type": "critic", "description": "review"},
            }
        ],
    )
    [ev async for ev in mapper.process("updates", {"model": {"messages": [task_ai]}})]
    child_ai = AIMessage(
        content="",
        tool_calls=[{"name": "think_tool", "id": "call_think", "args": {"reflection": "hmm"}}],
    )
    events = [ev async for ev in mapper.process("updates", {"tools": {"messages": [child_ai]}})]
    starts = [ev for ev in events if ev["event"] == "tool_call_started"]
    assert json.loads(starts[0]["data"])["role"] == "critic"
    refls = [ev for ev in events if ev["event"] == "reflection_logged"]
    assert json.loads(refls[0]["data"])["role"] == "critic"


@pytest.mark.asyncio
async def test_tool_call_completed_carries_status_and_duration():
    """ToolMessage emits tool_call_completed with status, preview, duration_ms ≥ 0."""
    from langchain_core.messages import AIMessage, ToolMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "internet_search", "id": "call_done", "args": {"query": "Z"}}],
    )
    [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]

    tool_msg = ToolMessage(content="result body", tool_call_id="call_done", name="internet_search")
    events = [ev async for ev in mapper.process("updates", {"tools": {"messages": [tool_msg]}})]
    completions = [ev for ev in events if ev["event"] == "tool_call_completed"]
    assert len(completions) == 1
    payload = json.loads(completions[0]["data"])
    assert payload["id"] == "call_done"
    assert payload["status"] == "ok"
    assert payload["result_preview"] == "result body"
    assert payload["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_tool_call_completed_marks_status_error():
    """ToolMessage with status='error' propagates as tool_call_completed status='error'."""
    from langchain_core.messages import AIMessage, ToolMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "read_file", "id": "call_err", "args": {"file_path": "/x"}}],
    )
    [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]

    tool_msg = ToolMessage(
        content="Error: not found",
        tool_call_id="call_err",
        name="read_file",
        status="error",
    )
    events = [ev async for ev in mapper.process("updates", {"tools": {"messages": [tool_msg]}})]
    completions = [ev for ev in events if ev["event"] == "tool_call_completed"]
    assert json.loads(completions[0]["data"])["status"] == "error"


@pytest.mark.asyncio
async def test_tool_call_started_dedupes_by_tool_call_id():
    """Re-broadcast of the same AIMessage must not emit duplicate starts."""
    from langchain_core.messages import AIMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "internet_search", "id": "call_dupe", "args": {}}],
    )
    first = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    second = [ev async for ev in mapper.process("updates", {"model": {"messages": [ai]}})]
    assert sum(1 for ev in first if ev["event"] == "tool_call_started") == 1
    assert sum(1 for ev in second if ev["event"] == "tool_call_started") == 0


@pytest.mark.asyncio
async def test_tool_call_completed_without_prior_start_is_skipped():
    """Defensive: a ToolMessage whose tool_call_id we never saw must not crash or emit."""
    from langchain_core.messages import ToolMessage

    from app.streaming.chunk_mapper import ChunkMapper

    mapper = ChunkMapper()
    tool_msg = ToolMessage(content="orphan", tool_call_id="call_orphan", name="internet_search")
    events = [ev async for ev in mapper.process("updates", {"tools": {"messages": [tool_msg]}})]
    assert all(ev["event"] != "tool_call_completed" for ev in events)
