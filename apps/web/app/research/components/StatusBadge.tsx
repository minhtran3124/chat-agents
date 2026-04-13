type Status = "idle" | "streaming" | "done" | "error";

const LABEL: Record<Status, string> = {
  idle: "Ready",
  streaming: "Researching",
  done: "Brief ready",
  error: "Stopped",
};

export function StatusBadge({ status }: { status: Status }) {
  const dot =
    status === "streaming"
      ? "bg-terracotta animate-soft-pulse"
      : status === "done"
        ? "bg-olive"
        : status === "error"
          ? "bg-danger"
          : "bg-subink/50";

  const text =
    status === "streaming"
      ? "text-terracotta"
      : status === "done"
        ? "text-olive"
        : status === "error"
          ? "text-danger"
          : "text-subink";

  const ring =
    status === "streaming"
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
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {LABEL[status]}
    </div>
  );
}
