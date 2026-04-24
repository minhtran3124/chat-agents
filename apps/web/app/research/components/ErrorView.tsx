import type { ErrorReason } from "@/lib/types";

type BudgetExceeded = { tokens_used: number; limit: number; message: string };

type ErrorViewProps = {
  error?: string;
  reason?: ErrorReason;
  recoverable?: boolean;
  budgetExceeded?: BudgetExceeded;
  onReset: () => void;
  onRetry?: () => void;
};

export function ErrorView({
  error,
  recoverable,
  budgetExceeded,
  onReset,
  onRetry,
}: ErrorViewProps) {
  if (budgetExceeded) {
    return <BudgetWarning data={budgetExceeded} onReset={onReset} />;
  }
  return (
    <ErrorPanel
      message={error ?? "Research stopped unexpectedly."}
      recoverable={recoverable === true}
      onReset={onReset}
      onRetry={onRetry}
    />
  );
}

function BudgetWarning({ data, onReset }: { data: BudgetExceeded; onReset: () => void }) {
  const pct = Math.min(100, (data.tokens_used / data.limit) * 100);
  return (
    <div className="mx-auto mt-10 max-w-xl rounded-lg border border-warn/40 bg-warn/10 p-6 text-warn">
      <div className="mb-2 flex items-center gap-2 font-mono text-[11px] uppercase tracking-caps">
        <WarningGlyph />
        Token budget exceeded
      </div>
      <p className="mb-4 text-sm text-ink">
        Run stopped at {data.tokens_used.toLocaleString()} / {data.limit.toLocaleString()} tokens.
        The partial report may be incomplete.
      </p>
      <div className="mb-4 h-1.5 w-full rounded-full bg-warn/20" data-testid="budget-progress">
        <div className="h-1.5 rounded-full bg-warn" style={{ width: `${pct}%` }} />
      </div>
      <div className="flex justify-end">
        <button
          onClick={onReset}
          className="rounded-md border border-hairline bg-canvas px-3.5 py-1.5 font-mono text-[11px] font-medium uppercase tracking-caps text-ink-muted transition hover:border-accent/40 hover:text-accent-deep focus:outline-none focus:ring-2 focus:ring-accent/30"
        >
          New research
        </button>
      </div>
    </div>
  );
}

function ErrorPanel({
  message,
  recoverable,
  onReset,
  onRetry,
}: {
  message: string;
  recoverable: boolean;
  onReset: () => void;
  onRetry?: () => void;
}) {
  return (
    <div className="mx-auto mt-10 max-w-xl rounded-lg border border-danger/40 bg-danger/5 p-6 text-danger">
      <div className="mb-2 flex items-center gap-2 font-mono text-[11px] uppercase tracking-caps">
        <ErrorGlyph />
        Research stopped
      </div>
      <p className="mb-4 text-sm text-ink">{message}</p>
      <div className="flex justify-end gap-2">
        {recoverable && onRetry ? (
          <button
            onClick={onRetry}
            className="rounded-md border border-danger/40 bg-canvas px-3.5 py-1.5 font-mono text-[11px] font-medium uppercase tracking-caps text-danger transition hover:bg-danger/10 focus:outline-none focus:ring-2 focus:ring-danger/30"
          >
            Try again
          </button>
        ) : null}
        <button
          onClick={onReset}
          className="rounded-md border border-hairline bg-canvas px-3.5 py-1.5 font-mono text-[11px] font-medium uppercase tracking-caps text-ink-muted transition hover:border-accent/40 hover:text-accent-deep focus:outline-none focus:ring-2 focus:ring-accent/30"
        >
          New research
        </button>
      </div>
    </div>
  );
}

function WarningGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden className="inline-block">
      <path d="M8 1.5l7 12H1l7-12z" fill="currentColor" fillOpacity="0.2" stroke="currentColor" />
      <path d="M8 6v4" stroke="currentColor" strokeLinecap="round" />
      <circle cx="8" cy="12" r="0.75" fill="currentColor" />
    </svg>
  );
}

function ErrorGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden className="inline-block">
      <circle cx="8" cy="8" r="7" fill="currentColor" fillOpacity="0.15" stroke="currentColor" />
      <path d="M5 5l6 6M11 5l-6 6" stroke="currentColor" strokeLinecap="round" />
    </svg>
  );
}
