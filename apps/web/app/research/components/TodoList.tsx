import { TodoItem } from "@/lib/types";
import { SectionHeader, EmptyHint } from "./_panel";

const STATUS_STYLE: Record<TodoItem["status"], { dot: string; text: string }> = {
  pending: { dot: "bg-ink-dim/50", text: "text-ink-muted" },
  in_progress: {
    dot: "bg-accent animate-soft-pulse",
    text: "text-ink font-medium",
  },
  completed: {
    dot: "bg-success/70",
    text: "text-ink-dim line-through decoration-ink-dim/40",
  },
};

export function TodoList({ items }: { items: TodoItem[] }) {
  const done = items.filter((t) => t.status === "completed").length;
  return (
    <section className="border-b border-hairline-soft p-6">
      <SectionHeader title="Plan" count={items.length > 0 ? `${done} / ${items.length}` : null} />
      {items.length === 0 ? (
        <EmptyHint>A plan will appear here as soon as research begins.</EmptyHint>
      ) : (
        <ol className="scrollbar-quiet max-h-80 space-y-2.5 overflow-y-auto pr-1 text-sm">
          {items.map((t, i) => {
            const s = STATUS_STYLE[t.status] ?? STATUS_STYLE.pending;
            return (
              <li
                key={i}
                className="animate-fade-in-up flex items-start gap-3 leading-snug"
                style={{ animationDelay: `${Math.min(i, 6) * 40}ms` }}
              >
                <span className={`mt-1.5 h-2 w-2 flex-none rounded-full ${s.dot}`} aria-hidden />
                <span className={s.text}>{t.content}</span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
