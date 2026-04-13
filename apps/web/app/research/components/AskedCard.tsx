type Status = "idle" | "loading" | "streaming" | "done" | "error";

/**
 * Pinned acknowledgment card — appears the instant the user hits Enter,
 * showing the question they asked plus a status-appropriate dot.  Stays
 * visible through loading / streaming / done so the user can always
 * see what the current brief is answering.
 */
export function AskedCard({
  question,
  status,
}: {
  question: string;
  status: Status;
}) {
  const dotClass =
    status === "loading"
      ? "bg-amber animate-soft-pulse"
      : status === "streaming"
        ? "bg-terracotta animate-soft-pulse"
        : status === "error"
          ? "bg-danger"
          : "bg-olive";

  const statusLabel =
    status === "loading"
      ? "Preparing"
      : status === "streaming"
        ? "Researching"
        : status === "error"
          ? "Stopped"
          : "Answered";

  return (
    <div className="animate-asked-slide border-b border-rule bg-cream px-8 py-4">
      <div className="flex items-start gap-4">
        <div className="mt-1 flex-none">
          <span
            className={`inline-block h-2 w-2 rounded-full ${dotClass}`}
            aria-hidden
          />
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-baseline gap-2">
            <span className="text-[10px] font-medium uppercase tracking-caps text-subink">
              You asked
            </span>
            <span className="text-[10px] uppercase tracking-caps text-subink/60">
              · {statusLabel}
            </span>
          </div>
          <p className="font-display text-base italic leading-snug text-ink">
            &ldquo;{question}&rdquo;
          </p>
        </div>
      </div>
    </div>
  );
}
