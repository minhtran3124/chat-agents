import { TodoItem } from "@/lib/types";

const ICON = { pending: "⏳", in_progress: "▶", done: "✓" } as const;

export function TodoList({ items }: { items: TodoItem[] }) {
  if (items.length === 0) return <Empty label="No plan yet" />;
  return (
    <Section title="📋 To-do">
      <ul className="space-y-1 text-sm">
        {items.map((t, i) => (
          <li key={i} className={t.status === "done" ? "opacity-50" : ""}>
            <span className="mr-2">{ICON[t.status]}</span>
            {t.text}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b p-3">
      <h3 className="mb-2 font-semibold">{title}</h3>
      {children}
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="border-b p-3 text-sm text-gray-400">{label}</div>;
}
