export type TodoStatus = "pending" | "in_progress" | "completed";
export type TodoItem = { content: string; status: TodoStatus };
export type FileRef = { path: string; size_tokens: number; preview: string };
export type SubagentRun = {
  id: string;
  name: string;
  task: string;
  status: "running" | "done";
  summary?: string;
};
export type CompressionEvent = {
  original_tokens: number;
  compressed_tokens: number;
  synthetic?: boolean;
};

export type AgentRole = "main" | "researcher" | "critic";
export type ReflectionRole = AgentRole;
export type Reflection = {
  role: ReflectionRole;
  reflection: string;
  at: number;
};

export type ToolCallStatus = "running" | "ok" | "error";

export type ToolCallNode = {
  id: string;
  role: AgentRole;
  toolName: string;
  argsPreview: string;
  status: ToolCallStatus;
  resultPreview?: string;
  durationMs?: number;
  parentId: string | null;
  childIds: string[];
  files: string[];
  startedAt: number;
};

export type ErrorReason = "timeout" | "internal" | "rate_limited";
export type FinalReportSource = "stream" | "file" | "error";

export type SSEEventMap = {
  stream_start: { thread_id: string; started_at: string };
  todo_updated: { items: TodoItem[] };
  file_saved: { path: string; size_tokens: number; preview: string };
  subagent_started: { id: string; name: string; task: string };
  subagent_completed: { id: string; summary: string };
  compression_triggered: CompressionEvent;
  text_delta: { content: string };
  reflection_logged: { role: ReflectionRole; reflection: string };
  tool_call_started: {
    id: string;
    role: AgentRole;
    tool_name: string;
    args_preview: string;
  };
  tool_call_completed: {
    id: string;
    status: "ok" | "error";
    result_preview: string;
    duration_ms: number;
  };
  error: { message: string; reason: ErrorReason; recoverable: boolean };
  budget_exceeded: { tokens_used: number; limit: number; message: string };
  token_breakdown: { breakdown: Record<AgentRole, number> };
  stream_end: {
    final_report: string;
    usage: Record<string, unknown>;
    versions_used: Record<string, string>;
    final_report_source?: FinalReportSource;
  };
};
