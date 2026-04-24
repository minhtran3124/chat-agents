import { Reflection } from "@/lib/types";

const ROLE_LABEL: Record<Reflection["role"], string> = {
  main: "Planner",
  researcher: "Researcher",
};

const ROLE_DOT: Record<Reflection["role"], string> = {
  main: "bg-subink",
  researcher: "bg-terracotta",
};

export function ReflectionPanel({ reflections }: { reflections: Reflection[] }) {
  return (
    <section className="border-b border-rule p-6">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-display text-base font-semibold tracking-tight">Reflections</h2>
        {reflections.length > 0 && (
          <span className="text-[10px] font-medium uppercase tracking-caps text-subink">
            {reflections.length} logged
          </span>
        )}
      </div>
      {reflections.length === 0 ? (
        <p className="text-sm italic leading-snug text-subink/80">
          Reflections appear as the agent reasons about gaps before each search.
        </p>
      ) : (
        <ol className="max-h-80 space-y-2.5 overflow-y-auto pr-1">
          {reflections.map((r, idx) => (
            <li
              key={`${r.at}-${idx}`}
              className="animate-fade-in-up rounded-sm border border-rule bg-paper/80 px-3.5 py-3 text-sm"
            >
              <div className="flex items-center gap-2">
                <span className={`h-2 w-2 flex-none rounded-full ${ROLE_DOT[r.role]}`} />
                <span className="font-display text-xs font-semibold uppercase tracking-caps text-ink">
                  {ROLE_LABEL[r.role]}
                </span>
                <span className="ml-auto text-[10px] uppercase tracking-caps text-subink">
                  #{idx + 1}
                </span>
              </div>
              <p className="mt-2 leading-snug text-subink">{r.reflection}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
