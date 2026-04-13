"use client";
import { useResearchStream } from "@/lib/useResearchStream";
import { QuestionForm } from "./components/QuestionForm";
import { TodoList } from "./components/TodoList";
import { FileList } from "./components/FileList";
import { SubagentPanel } from "./components/SubagentPanel";
import { ReportView } from "./components/ReportView";
import { StatusBadge } from "./components/StatusBadge";

export default function ResearchPage() {
  const { state, start, reset } = useResearchStream();
  const busy = state.status === "streaming";
  return (
    <div className="flex h-screen flex-col bg-cream text-ink">
      <header className="flex items-start justify-between gap-6 border-b border-rule px-8 pb-5 pt-7">
        <div>
          <div className="mb-1 text-[10px] font-medium uppercase tracking-caps text-subink">
            Deep research
          </div>
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">
            Research Notebook
          </h1>
          <p className="mt-1 max-w-xl text-sm leading-snug text-subink">
            Ask a question. Watch a plan form, researchers dig in, and a brief write itself.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {state.status !== "idle" && (
            <button
              onClick={reset}
              className="rounded-sm border border-rule bg-paper px-4 py-2 font-display text-sm font-medium text-subink transition hover:border-terracotta hover:text-terracotta focus:outline-none focus:ring-2 focus:ring-terracotta/40"
            >
              New research
            </button>
          )}
          <StatusBadge status={state.status} />
        </div>
      </header>

      <QuestionForm onSubmit={start} disabled={busy} />

      <main className="flex min-h-0 flex-1">
        <aside className="w-96 flex-shrink-0 overflow-y-auto border-r border-rule bg-paper/30">
          <TodoList items={state.todos} />
          <SubagentPanel runs={state.subagents} compressions={state.compressions} />
          <FileList files={state.files} />
        </aside>
        <section className="min-w-0 flex-1 overflow-y-auto">
          <ReportView text={state.report} status={state.status} />
        </section>
      </main>

      {state.error && (
        <div className="border-t border-rule bg-[#f6e3df] px-6 py-3 text-sm text-danger">
          <span className="mr-2 font-medium">Something went wrong.</span>
          {state.error}
        </div>
      )}
    </div>
  );
}
