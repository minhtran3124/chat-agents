import { TodoItem } from "@/lib/types";

const STATUS_STYLE: Record<TodoItem["status"], { dot: string; text: string }> = {
  pending: { dot: "bg-rule", text: "text-subink" },
  in_progress: { dot: "bg-terracotta animate-soft-pulse", text: "text-ink font-medium" },
  completed: { dot: "bg-olive", text: "text-subink line-through" },
};

export function TodoList({ items }: { items: TodoItem[] }) {
  const done = items.filter((t) => t.status === "completed").length;
  return (
    <section className="border-b border-rule p-6">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-display text-base font-semibold tracking-tight">Plan</h2>
        {items.length > 0 && (
          <span className="text-xs tabular-nums text-subink">
            {done} / {items.length}
          </span>
        )}
      </div>
      {items.length === 0 ? (
        <p className="text-sm italic leading-snug text-subink/80">
          A plan will appear here as soon as research begins.
        </p>
      ) : (
        <ol className="max-h-80 space-y-2.5 overflow-y-auto pr-1 text-sm">
          {items.map((t, i) => {
            const s = STATUS_STYLE[t.status] ?? STATUS_STYLE.pending;
            return (
              <li
                key={i}
                className="animate-fade-in-up flex items-start gap-3 leading-snug"
                style={{ animationDelay: `${Math.min(i, 6) * 40}ms` }}
              >
                <span
                  className={`mt-1.5 h-2 w-2 flex-none rounded-full ${s.dot}`}
                  aria-hidden
                />
                <span className={s.text}>{t.content}</span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
