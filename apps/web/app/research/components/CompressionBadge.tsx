import { CompressionEvent } from "@/lib/types";
import { Pill } from "./_panel";

export function CompressionBadge({ events }: { events: CompressionEvent[] }) {
  if (events.length === 0) return null;
  const synthetic = events.some((e) => e.synthetic);
  return (
    <Pill tone="warn" className="ml-2">
      <span title={synthetic ? "Estimated (synthetic)" : "Detected from token drop"}>
        Memory · {events.length}
      </span>
    </Pill>
  );
}
