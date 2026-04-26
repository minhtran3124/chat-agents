"use client";
import { useEffect, useRef, useState } from "react";
import { useResearchStream } from "@/lib/useResearchStream";
import { QuestionForm } from "./components/QuestionForm";
import { TodoList } from "./components/TodoList";
import { FileList } from "./components/FileList";
import { SubagentPanel } from "./components/SubagentPanel";
import { ReflectionPanel } from "./components/ReflectionPanel";
import { TokenBreakdownPanel } from "./components/TokenBreakdownPanel";
import { ReportView } from "./components/ReportView";
import { StatusBadge } from "./components/StatusBadge";
import { ToastStack, ToastItem } from "./components/SubagentToast";
import { AskedCard } from "./components/AskedCard";
import { ErrorView } from "./components/ErrorView";
import { WorkflowTree } from "./components/WorkflowTree";

export default function ResearchPage() {
  const { state, start, reset } = useResearchStream();
  const busy = state.status === "streaming" || state.status === "loading";
  const loading = state.status === "loading";

  // Ephemeral toast notifications — one per subagent completion, 5s TTL.
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const notifiedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const newlyDone: ToastItem[] = [];
    for (const agent of Object.values(state.subagents)) {
      if (agent.status === "done" && !notifiedRef.current.has(agent.id)) {
        notifiedRef.current.add(agent.id);
        newlyDone.push({ id: agent.id, name: agent.name, task: agent.task });
      }
    }
    if (newlyDone.length > 0) {
      setToasts((prev) => [...prev, ...newlyDone]);
    }
  }, [state.subagents]);

  useEffect(() => {
    if (state.status === "idle") {
      notifiedRef.current.clear();
      setToasts([]);
    }
  }, [state.status]);

  function dismissToast(id: string) {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }

  return (
    <div className="flex h-screen flex-col bg-canvas text-ink">
      <header className="flex items-center justify-between gap-6 border-b border-hairline px-8 py-4">
        <div className="flex items-center gap-3">
          <JournalMark />
          <div className="flex items-baseline gap-2.5">
            <span className="text-[15px] font-semibold tracking-tight text-ink">
              Research Journal
            </span>
            <span className="font-mono text-[10px] uppercase tracking-caps text-ink-dim">
              Deep research
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {state.status !== "idle" && (
            <button
              onClick={reset}
              className="rounded-md border border-hairline bg-canvas px-3.5 py-1.5 font-mono text-[11px] font-medium uppercase tracking-caps text-ink-muted transition hover:border-accent/40 hover:text-accent-deep focus:outline-none focus:ring-2 focus:ring-accent/30"
            >
              New research
            </button>
          )}
          <StatusBadge status={state.status} />
        </div>
      </header>

      <QuestionForm onSubmit={start} disabled={busy} loading={loading} />

      {/* Pinned acknowledgment card — the "immediate indicator" that
          appears the instant Enter is pressed and persists through the
          whole run. */}
      {state.question && state.status !== "idle" && (
        <AskedCard question={state.question} status={state.status} />
      )}

      {/* indeterminate loading bar — only visible during "loading" phase */}
      {loading && <div className="loading-bar" aria-hidden />}

      <main className="flex min-h-0 flex-1">
        <aside className="scrollbar-quiet w-[360px] flex-shrink-0 overflow-y-auto border-r border-hairline bg-surface/50">
          <TodoList items={state.todos} />
          <SubagentPanel runs={state.subagents} compressions={state.compressions} />
          <TokenBreakdownPanel breakdown={state.tokenBreakdown} />
          <ReflectionPanel reflections={state.reflections} />
          <FileList files={state.files} />
        </aside>
        <div className="flex min-w-0 flex-1 gap-px bg-hairline">
          <section className="scrollbar-quiet min-w-0 flex-1 overflow-y-auto bg-canvas">
            <WorkflowTree workflow={state.workflow} />
          </section>
          <section className="scrollbar-quiet min-w-0 flex-1 overflow-y-auto bg-canvas">
            {state.status === "error" ? (
              <ErrorView
                error={state.error}
                reason={state.errorReason}
                recoverable={state.errorRecoverable}
                budgetExceeded={state.budgetExceeded}
                onReset={reset}
              />
            ) : (
              <ReportView text={state.report} status={state.status} source={state.reportSource} />
            )}
          </section>
        </div>
      </main>

      <ToastStack items={toasts} onDismiss={dismissToast} />
    </div>
  );
}

/**
 * A small identity mark — stacked horizontal lines fanning into an arrow,
 * echoing "a journal being written." Teal stroke, 24px.
 */
function JournalMark() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden
      className="text-accent"
    >
      <path d="M4 6h12" />
      <path d="M4 11h14" />
      <path d="M4 16h9" />
      <path d="M15 16l3 3 3-5" />
    </svg>
  );
}
