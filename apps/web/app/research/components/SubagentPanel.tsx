import { SubagentRun, CompressionEvent } from "@/lib/types";

export function SubagentPanel({
  runs,
  compressions,
}: {
  runs: Record<string, SubagentRun>;
  compressions: CompressionEvent[];
}) {
  const list = Object.values(runs);
  return (
    <section className="border-b border-rule p-6">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-display text-base font-semibold tracking-tight">Researchers</h2>
        {compressions.length > 0 && (
          <span className="rounded-full bg-amber/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-caps text-amber">
            Memory refreshed ×{compressions.length}
          </span>
        )}
      </div>
      {list.length === 0 ? (
        <p className="text-sm italic leading-snug text-subink/80">
          When a specialist is called in, you&rsquo;ll see their task here.
        </p>
      ) : (
        <ul className="max-h-80 space-y-2.5 overflow-y-auto pr-1">
          {list.map((r) => (
            <li
              key={r.id}
              className="animate-fade-in-up rounded-sm border border-rule bg-paper/80 px-3.5 py-3 text-sm"
            >
              <div className="flex items-center gap-2">
                <span
                  className={`h-2 w-2 flex-none rounded-full ${
                    r.status === "running" ? "animate-soft-pulse bg-terracotta" : "bg-olive"
                  }`}
                />
                <span className="font-display text-sm font-semibold capitalize tracking-tight text-ink">
                  {r.name}
                </span>
                <span className="ml-auto text-[10px] uppercase tracking-caps text-subink">
                  {r.status === "running" ? "working" : "done"}
                </span>
              </div>
              <p className="mt-2 line-clamp-3 leading-snug text-subink">{r.task}</p>
              {r.summary && (
                <p className="mt-2.5 line-clamp-3 border-t border-rule pt-2.5 text-xs leading-snug text-ink/75">
                  {r.summary}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
