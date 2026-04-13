import { SubagentRun, CompressionEvent } from "@/lib/types";
import { CompressionBadge } from "./CompressionBadge";

export function SubagentPanel({
  runs,
  compressions,
}: {
  runs: Record<string, SubagentRun>;
  compressions: CompressionEvent[];
}) {
  const list = Object.values(runs);
  return (
    <div className="border-b p-3">
      <h3 className="mb-2 font-semibold">
        🤖 Subagents <CompressionBadge events={compressions} />
      </h3>
      {list.length === 0 ? (
        <div className="text-sm text-gray-400">None spawned yet</div>
      ) : (
        <ul className="space-y-1 text-sm">
          {list.map((r) => (
            <li key={r.id}>
              <span className="font-mono">{r.name}</span>{" "}
              <span className="text-gray-500">{r.task}</span>{" "}
              <span>{r.status === "done" ? "✓" : "⏳"}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
