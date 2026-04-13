export type TodoStatus = "pending" | "in_progress" | "done";
export type TodoItem = { text: string; status: TodoStatus };
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

export type SSEEventMap = {
  stream_start: { thread_id: string; started_at: string };
  todo_updated: { items: TodoItem[] };
  file_saved: { path: string; size_tokens: number; preview: string };
  subagent_started: { id: string; name: string; task: string };
  subagent_completed: { id: string; summary: string };
  compression_triggered: CompressionEvent;
  text_delta: { content: string };
  memory_updated: { namespace: string; key: string };
  error: { message: string; recoverable: boolean };
  stream_end: { final_report: string; usage: Record<string, unknown> };
};
