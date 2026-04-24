type Status = "idle" | "loading" | "streaming" | "done" | "error";

/**
 * Pinned acknowledgment card — appears the instant the user hits Enter,
 * showing the question they asked plus a status-appropriate dot.  Stays
 * visible through loading / streaming / done so the user can always
 * see what the current brief is answering.
 */
export function AskedCard({ question, status }: { question: string; status: Status }) {
  const dotClass =
    status === "loading"
      ? "bg-warn animate-soft-pulse"
      : status === "streaming"
        ? "bg-accent animate-soft-pulse"
        : status === "error"
          ? "bg-danger"
          : "bg-success";

  const statusLabel =
    status === "loading"
      ? "Preparing"
      : status === "streaming"
        ? "Researching"
        : status === "error"
          ? "Stopped"
          : "Answered";

  return (
    <div className="animate-asked-slide border-b border-hairline bg-surface/60 px-8 py-4">
      <div className="flex items-start gap-4">
        <div className="mt-2 flex-none">
          <span className={`inline-block h-2 w-2 rounded-full ${dotClass}`} aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-baseline gap-2">
            <span className="font-mono text-[10px] font-medium uppercase tracking-caps text-ink-dim">
              You asked
            </span>
            <span className="font-mono text-[10px] uppercase tracking-caps text-ink-dim/70">
              · {statusLabel}
            </span>
          </div>
          <p className="font-display text-[17px] italic leading-snug text-ink">
            &ldquo;{question}&rdquo;
          </p>
        </div>
      </div>
    </div>
  );
}
