"use client";
import { useResearchStream } from "@/lib/useResearchStream";
import { QuestionForm } from "./components/QuestionForm";
import { TodoList } from "./components/TodoList";
import { FileList } from "./components/FileList";
import { SubagentPanel } from "./components/SubagentPanel";
import { ReportView } from "./components/ReportView";

export default function ResearchPage() {
  const { state, start } = useResearchStream();
  const busy = state.status === "streaming";
  return (
    <div className="flex h-screen flex-col">
      <header className="border-b px-4 py-3">
        <h1 className="text-lg font-semibold">Deep Agents Research Assistant</h1>
      </header>
      <QuestionForm onSubmit={start} disabled={busy} />
      <main className="flex min-h-0 flex-1">
        <aside className="w-80 overflow-y-auto border-r">
          <TodoList items={state.todos} />
          <FileList files={state.files} />
          <SubagentPanel runs={state.subagents} compressions={state.compressions} />
        </aside>
        <section className="min-w-0 flex-1">
          <ReportView text={state.report} />
        </section>
      </main>
      {state.error && <div className="bg-red-100 p-3 text-sm text-red-800">{state.error}</div>}
    </div>
  );
}
