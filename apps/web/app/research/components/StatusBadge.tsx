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
      ? "bg-amber animate-soft-pulse"
      : status === "streaming"
        ? "bg-terracotta animate-soft-pulse"
        : status === "done"
          ? "bg-olive"
          : status === "error"
            ? "bg-danger"
            : "bg-subink/50";

  const text =
    status === "loading"
      ? "text-amber"
      : status === "streaming"
        ? "text-terracotta"
        : status === "done"
          ? "text-olive"
          : status === "error"
            ? "text-danger"
            : "text-subink";

  const ring =
    status === "loading"
      ? "ring-amber/30"
      : status === "streaming"
        ? "ring-terracotta/30"
        : status === "done"
          ? "ring-olive/30"
          : status === "error"
            ? "ring-danger/30"
            : "ring-rule";

  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full bg-paper px-3.5 py-1.5 text-xs font-medium uppercase tracking-caps ring-1 ${ring} ${text}`}
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
      className="animate-spin-slow h-3 w-3 text-amber"
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
