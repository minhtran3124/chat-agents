"use client";
import { AgentRole } from "@/lib/types";

interface TokenBreakdownPanelProps {
  breakdown?: Record<AgentRole, number>;
}

const ROLE_LABELS: Record<AgentRole, string> = {
  main: "Main Agent",
  researcher: "Researcher",
  critic: "Critic",
};

const ROLE_COLORS: Record<AgentRole, string> = {
  main: "bg-blue-50 border-blue-100 text-blue-900",
  researcher: "bg-purple-50 border-purple-100 text-purple-900",
  critic: "bg-amber-50 border-amber-100 text-amber-900",
};

export function TokenBreakdownPanel({ breakdown }: TokenBreakdownPanelProps) {
  if (!breakdown || Object.values(breakdown).every((v) => v === 0)) {
    return null;
  }

  const total = Object.values(breakdown).reduce((a, b) => a + b, 0);
  const sorted = (Object.entries(breakdown) as Array<[AgentRole, number]>).sort(
    ([, a], [, b]) => b - a,
  );

  return (
    <div className="border-b border-hairline px-6 py-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Token Usage
        </h3>
        <span className="text-xs font-semibold text-ink">{total.toLocaleString()} tokens</span>
      </div>
      <div className="space-y-2">
        {sorted.map(([role, tokens]) => (
          <div key={role}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="font-medium text-ink-muted">{ROLE_LABELS[role]}</span>
              <span className="font-mono font-semibold text-ink">{tokens.toLocaleString()}</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-hairline">
              <div
                className={`h-full ${ROLE_COLORS[role]} border border-current`}
                style={{ width: `${(tokens / total) * 100}%` }}
              />
            </div>
            <div className="mt-0.5 text-xs text-ink-dim">
              {((tokens / total) * 100).toFixed(1)}%
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
