import { describe, expect, it } from "vitest";
import { reducer, initial } from "./useResearchStream";

describe("research reducer", () => {
  it("stream_start resets to streaming state", () => {
    const after = reducer(
      { ...initial, report: "old" },
      { event: "stream_start", data: { thread_id: "t", started_at: "now" } },
    );
    expect(after.status).toBe("streaming");
    expect(after.report).toBe("");
  });

  it("loading_start sets status to loading and clears previous state", () => {
    const after = reducer(
      { ...initial, report: "stale", status: "done" },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      { event: "loading_start", data: {} } as any,
    );
    expect(after.status).toBe("loading");
    expect(after.report).toBe("");
  });

  it("todo_updated replaces items", () => {
    const after = reducer(initial, {
      event: "todo_updated",
      data: { items: [{ content: "a", status: "pending" }] },
    });
    expect(after.todos).toHaveLength(1);
  });

  it("file_saved upserts by path (no duplicates)", () => {
    let s = reducer(initial, {
      event: "file_saved",
      data: { path: "vfs://a", size_tokens: 100, preview: "x" },
    });
    s = reducer(s, {
      event: "file_saved",
      data: { path: "vfs://a", size_tokens: 200, preview: "x" },
    });
    expect(s.files).toHaveLength(1);
    expect(s.files[0].size_tokens).toBe(200);
  });

  it("subagent_started then subagent_completed updates same id", () => {
    let s = reducer(initial, {
      event: "subagent_started",
      data: { id: "r1", name: "researcher", task: "X" },
    });
    expect(s.subagents["r1"].status).toBe("running");
    s = reducer(s, {
      event: "subagent_completed",
      data: { id: "r1", summary: "done" },
    });
    expect(s.subagents["r1"].status).toBe("done");
    expect(s.subagents["r1"].summary).toBe("done");
  });

  it("text_delta appends to report", () => {
    let s = reducer(initial, { event: "text_delta", data: { content: "Hello " } });
    s = reducer(s, { event: "text_delta", data: { content: "world" } });
    expect(s.report).toBe("Hello world");
  });

  it("compression_triggered appends events", () => {
    const s = reducer(initial, {
      event: "compression_triggered",
      data: { original_tokens: 100, compressed_tokens: 50, synthetic: true },
    });
    expect(s.compressions).toHaveLength(1);
    expect(s.compressions[0].synthetic).toBe(true);
  });

  it("error sets error status and message", () => {
    const s = reducer(initial, {
      event: "error",
      data: { message: "boom", recoverable: false },
    });
    expect(s.status).toBe("error");
    expect(s.error).toBe("boom");
  });

  it("stream_end transitions to done with final_report override", () => {
    const s = reducer(
      { ...initial, report: "partial" },
      { event: "stream_end", data: { final_report: "complete", usage: {} } },
    );
    expect(s.status).toBe("done");
    expect(s.report).toBe("complete");
  });

  it("stream_end marks all pending/in_progress todos as completed", () => {
    const withTodos = {
      ...initial,
      todos: [
        { content: "a", status: "completed" as const },
        { content: "b", status: "in_progress" as const },
        { content: "c", status: "pending" as const },
      ],
    };
    const s = reducer(withTodos, { event: "stream_end", data: { final_report: "", usage: {} } });
    expect(s.todos.every((t) => t.status === "completed")).toBe(true);
  });

  it("unknown event is a no-op", () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const s = reducer(initial, { event: "unknown_xyz", data: {} } as any);
    expect(s).toBe(initial);
  });

  it("intent_classified sets routedIntent", () => {
    const s = reducer(initial, {
      event: "intent_classified",
      data: { intent: "deep-research", confidence: 1.0, fallback_used: false },
    });
    expect(s.routedIntent).toBe("deep-research");
  });

  it("intent_classified updates routedIntent on second event", () => {
    let s = reducer(initial, {
      event: "intent_classified",
      data: { intent: "chat", confidence: 0.9, fallback_used: false },
    });
    expect(s.routedIntent).toBe("chat");
    s = reducer(s, {
      event: "intent_classified",
      data: { intent: "research", confidence: 0.8, fallback_used: false },
    });
    expect(s.routedIntent).toBe("research");
  });

  it("stream_start resets routedIntent to null", () => {
    const withIntent = { ...initial, routedIntent: "chat" };
    const s = reducer(withIntent, {
      event: "stream_start",
      data: { thread_id: "t", started_at: "now" },
    });
    expect(s.routedIntent).toBeNull();
  });
});
