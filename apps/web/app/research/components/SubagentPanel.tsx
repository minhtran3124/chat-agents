import { SubagentRun, CompressionEvent } from "@/lib/types";
import { EmptyHint, PanelCard, Pill } from "./_panel";

export function SubagentPanel({
  runs,
  compressions,
}: {
  runs: Record<string, SubagentRun>;
  compressions: CompressionEvent[];
}) {
  const list = Object.values(runs);
  return (
    <section className="border-b border-hairline-soft p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-mono text-[10px] font-semibold uppercase tracking-caps text-ink-muted">
          Researchers
        </h2>
        {compressions.length > 0 && <Pill tone="warn">Memory · {compressions.length}</Pill>}
      </div>
      {list.length === 0 ? (
        <EmptyHint>When a specialist is called in, you&rsquo;ll see their task here.</EmptyHint>
      ) : (
        <ul className="scrollbar-quiet max-h-80 space-y-2 overflow-y-auto pr-1">
          {list.map((r) => (
            <PanelCard key={r.id}>
              <div className="flex items-center gap-2">
                <span
                  className={`h-2 w-2 flex-none rounded-full ${
                    r.status === "running" ? "animate-soft-pulse bg-accent" : "bg-success/70"
                  }`}
                />
                <span className="text-sm font-semibold capitalize text-ink">{r.name}</span>
                <span className="ml-auto font-mono text-[9px] uppercase tracking-caps text-ink-dim">
                  {r.status === "running" ? "working" : "done"}
                </span>
              </div>
              <p className="mt-2 line-clamp-3 leading-snug text-ink-muted">{r.task}</p>
              {r.summary && (
                <p className="mt-2.5 line-clamp-3 border-t border-hairline-soft pt-2.5 text-xs leading-snug text-ink/80">
                  {r.summary}
                </p>
              )}
            </PanelCard>
          ))}
        </ul>
      )}
    </section>
  );
}
