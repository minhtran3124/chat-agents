type Status = "idle" | "loading" | "streaming" | "done" | "error";

const LABEL: Record<Status, string> = {
  idle: "Ready",
  loading: "Preparing",
  streaming: "Researching",
  done: "Brief ready",
  error: "Stopped",
};

export function StatusBadge({ status }: { status: Status }) {
  const dot =
    status === "loading"
      ? "bg-warn animate-soft-pulse"
      : status === "streaming"
        ? "bg-accent animate-soft-pulse"
        : status === "done"
          ? "bg-success"
          : status === "error"
            ? "bg-danger"
            : "bg-ink-dim";

  const text =
    status === "loading"
      ? "text-warn"
      : status === "streaming"
        ? "text-accent-deep"
        : status === "done"
          ? "text-success"
          : status === "error"
            ? "text-danger"
            : "text-ink-muted";

  const border =
    status === "loading"
      ? "border-warn/30"
      : status === "streaming"
        ? "border-accent/30"
        : status === "done"
          ? "border-success/30"
          : status === "error"
            ? "border-danger/30"
            : "border-hairline";

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full border bg-canvas px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-caps ${border} ${text}`}
    >
      {status === "loading" ? (
        <LoadingSpinner />
      ) : (
        <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      )}
      {LABEL[status]}
    </div>
  );
}

function LoadingSpinner() {
  return (
    <svg
      className="animate-spin-slow h-3 w-3 text-warn"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.25" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
