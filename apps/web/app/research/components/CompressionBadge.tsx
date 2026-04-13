import { CompressionEvent } from "@/lib/types";

export function CompressionBadge({ events }: { events: CompressionEvent[] }) {
  if (events.length === 0) return null;
  const synthetic = events.some((e) => e.synthetic);
  return (
    <span
      className="ml-2 rounded bg-purple-100 px-2 py-0.5 text-xs text-purple-800"
      title={synthetic ? "Estimated (synthetic)" : "Detected from token drop"}
    >
      🗜 {events.length} compression{events.length > 1 ? "s" : ""}
    </span>
  );
}
