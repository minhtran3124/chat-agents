"use client";
import { useReducer, useRef } from "react";
import { consumeFrames, leftoverAfterFrames, SSEFrame } from "./sseParser";
import {
  TodoItem,
  FileRef,
  SubagentRun,
  CompressionEvent,
  Reflection,
  ErrorReason,
  ToolCallNode,
  AgentRole,
} from "./types";

function newThreadId(): string {
  return crypto.randomUUID();
}

export type ReportSource = "stream" | "file" | "error";

export type WorkflowState = {
  nodes: Record<string, ToolCallNode>;
  rootIds: string[];
  taskStack: string[];
  lastNonTaskCallId: string | null;
};

const emptyWorkflow: WorkflowState = {
  nodes: {},
  rootIds: [],
  taskStack: [],
  lastNonTaskCallId: null,
};

export type ResearchState = {
  todos: TodoItem[];
  files: FileRef[];
  subagents: Record<string, SubagentRun>;
  compressions: CompressionEvent[];
  reflections: Reflection[];
  workflow: WorkflowState;
  report: string;
  reportSource: ReportSource | null;
  status: "idle" | "loading" | "streaming" | "done" | "error";
  question?: string;
  error?: string;
  errorReason?: ErrorReason;
  errorRecoverable?: boolean;
  budgetExceeded?: { tokens_used: number; limit: number; message: string };
  tokenBreakdown?: Record<AgentRole, number>;
};

export const initial: ResearchState = {
  todos: [],
  files: [],
  subagents: {},
  compressions: [],
  reflections: [],
  workflow: emptyWorkflow,
  report: "",
  reportSource: null,
  status: "idle",
};

export function reducer(state: ResearchState, frame: SSEFrame): ResearchState {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = frame.data as any;
  switch (frame.event) {
    case "reset":
      return initial;
    case "loading_start":
      return { ...initial, status: "loading", question: data.question };
    case "stream_start":
      return { ...initial, status: "streaming", question: state.question };
    case "todo_updated":
      return { ...state, todos: data.items };
    case "file_saved": {
      const nextFiles = [...state.files.filter((f) => f.path !== data.path), data];
      const ownerId = state.workflow.lastNonTaskCallId;
      if (!ownerId || !state.workflow.nodes[ownerId]) {
        return { ...state, files: nextFiles };
      }
      const owner = state.workflow.nodes[ownerId];
      if (owner.files.includes(data.path)) {
        return { ...state, files: nextFiles };
      }
      return {
        ...state,
        files: nextFiles,
        workflow: {
          ...state.workflow,
          nodes: {
            ...state.workflow.nodes,
            [ownerId]: { ...owner, files: [...owner.files, data.path] },
          },
        },
      };
    }
    case "tool_call_started": {
      if (state.workflow.nodes[data.id]) return state;
      const parentId = state.workflow.taskStack[state.workflow.taskStack.length - 1] ?? null;
      const node: ToolCallNode = {
        id: data.id,
        role: data.role,
        toolName: data.tool_name,
        argsPreview: data.args_preview,
        status: "running",
        parentId,
        childIds: [],
        files: [],
        startedAt: Date.now(),
      };
      const nodes: Record<string, ToolCallNode> = {
        ...state.workflow.nodes,
        [data.id]: node,
      };
      let rootIds = state.workflow.rootIds;
      if (parentId) {
        const parent = nodes[parentId];
        if (parent) {
          nodes[parentId] = { ...parent, childIds: [...parent.childIds, data.id] };
        }
      } else {
        rootIds = [...rootIds, data.id];
      }
      const isTask = data.tool_name === "task";
      return {
        ...state,
        workflow: {
          nodes,
          rootIds,
          taskStack: isTask ? [...state.workflow.taskStack, data.id] : state.workflow.taskStack,
          lastNonTaskCallId: isTask ? state.workflow.lastNonTaskCallId : data.id,
        },
      };
    }
    case "tool_call_completed": {
      const node = state.workflow.nodes[data.id];
      if (!node) return state;
      const updated: ToolCallNode = {
        ...node,
        status: data.status,
        resultPreview: data.result_preview,
        durationMs: data.duration_ms,
      };
      const isTaskTop = state.workflow.taskStack[state.workflow.taskStack.length - 1] === data.id;
      return {
        ...state,
        workflow: {
          ...state.workflow,
          nodes: { ...state.workflow.nodes, [data.id]: updated },
          taskStack: isTaskTop ? state.workflow.taskStack.slice(0, -1) : state.workflow.taskStack,
          lastNonTaskCallId:
            state.workflow.lastNonTaskCallId === data.id ? null : state.workflow.lastNonTaskCallId,
        },
      };
    }
    case "subagent_started":
      return {
        ...state,
        subagents: { ...state.subagents, [data.id]: { ...data, status: "running" } },
      };
    case "subagent_completed":
      return {
        ...state,
        subagents: {
          ...state.subagents,
          [data.id]: { ...state.subagents[data.id], status: "done", summary: data.summary },
        },
      };
    case "compression_triggered":
      return { ...state, compressions: [...state.compressions, data] };
    case "reflection_logged":
      return {
        ...state,
        reflections: [
          ...state.reflections,
          { role: data.role, reflection: data.reflection, at: Date.now() },
        ],
      };
    case "text_delta":
      return { ...state, report: state.report + data.content };
    case "error":
      return {
        ...state,
        status: "error",
        error: data.message,
        errorReason: data.reason,
        errorRecoverable: data.recoverable,
      };
    case "budget_exceeded":
      return {
        ...state,
        status: "error",
        budgetExceeded: data,
        error: data.message,
        errorRecoverable: false,
      };
    case "token_breakdown":
      return { ...state, tokenBreakdown: data.breakdown };
    case "stream_end":
      // Error path: `error` event already set status:"error". stream_end is
      // just the terminal signal — freeze partial state, do NOT flip to "done",
      // do NOT force-complete todos.
      //
      // DESIGN: see docs/superpowers/specs/2026-04-24-phase-0-stabilize-sse-contract-design.md §4.3
      if (data.final_report_source === "error") {
        return { ...state, reportSource: "error" };
      }
      return {
        ...state,
        status: "done",
        report: data.final_report || state.report,
        // If the backend reconstructed the report from draft.md (fallback
        // path), mark it so the UI can badge it as such; otherwise treat
        // as streamed.
        reportSource: data.final_report
          ? ((data.final_report_source as ReportSource | undefined) ?? "stream")
          : (state.reportSource ?? "stream"),
        // Mark any remaining pending/in_progress todos as completed — the
        // agent doesn't always re-call write_todos at the end of each step.
        todos: state.todos.map((t) =>
          t.status !== "completed" ? { ...t, status: "completed" as const } : t,
        ),
      };
    default:
      return state;
  }
}

export function useResearchStream() {
  const [state, dispatch] = useReducer(reducer, initial);
  const controller = useRef<AbortController | null>(null);

  async function start(question: string) {
    controller.current?.abort();
    controller.current = new AbortController();
    // Flip to "loading" immediately so the UI shows a spinner while the
    // request is in flight, before the first SSE event arrives.  Include
    // the question so the page can render a pinned "asked" card as
    // acknowledgement the instant Enter is pressed.
    dispatch({ event: "loading_start", data: { question } } as SSEFrame);
    const res = await fetch("/api/research", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, thread_id: newThreadId() }),
      signal: controller.current.signal,
    });
    if (!res.body) return;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      for (const frame of consumeFrames(buf)) dispatch(frame);
      buf = leftoverAfterFrames(buf);
    }
  }

  function stop() {
    controller.current?.abort();
  }

  function reset() {
    controller.current?.abort();
    dispatch({ event: "reset", data: {} } as SSEFrame);
  }

  return { state, start, stop, reset };
}
