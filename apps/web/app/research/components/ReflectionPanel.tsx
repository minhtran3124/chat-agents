import { Reflection } from "@/lib/types";
import { SectionHeader, EmptyHint, PanelCard } from "./_panel";

const ROLE_LABEL: Record<Reflection["role"], string> = {
  main: "Planner",
  researcher: "Researcher",
  critic: "Critic",
};

const ROLE_DOT: Record<Reflection["role"], string> = {
  main: "bg-ink-muted/70",
  researcher: "bg-accent",
  critic: "bg-warn",
};

export function ReflectionPanel({ reflections }: { reflections: Reflection[] }) {
  return (
    <section className="border-b border-hairline-soft p-6">
      <SectionHeader
        title="Reflections"
        count={reflections.length > 0 ? `${reflections.length}` : null}
      />
      {reflections.length === 0 ? (
        <EmptyHint>
          Reflections appear as the agent reasons about gaps before each search.
        </EmptyHint>
      ) : (
        <ol className="scrollbar-quiet max-h-80 space-y-2 overflow-y-auto pr-1">
          {reflections.map((r, idx) => (
            <PanelCard key={`${r.at}-${idx}`}>
              <div className="flex items-center gap-2">
                <span className={`h-2 w-2 flex-none rounded-full ${ROLE_DOT[r.role]}`} />
                <span className="font-mono text-[10px] font-semibold uppercase tracking-caps text-ink">
                  {ROLE_LABEL[r.role]}
                </span>
                <span className="ml-auto font-mono text-[9px] uppercase tracking-caps text-ink-dim">
                  #{idx + 1}
                </span>
              </div>
              <p className="mt-2 leading-snug text-ink-muted">{r.reflection}</p>
            </PanelCard>
          ))}
        </ol>
      )}
    </section>
  );
}
