"use client";
import { useEffect, useState } from "react";

export type ToastItem = {
  id: string;
  name: string;
  task?: string;
};

/**
 * A single toast card.  Lifecycle:
 *   1. mount  → toast-enter (slide in + fade)
 *   2. +4.6s  → trigger toast-exit (slide out + fade)
 *   3. +5.0s  → parent removes from list
 * The 400 ms exit animation piggybacks on the 5 s total TTL by starting
 * at 4.6 s so the visual exit is fully complete at 5 s.
 */
function Toast({ item, onDismiss }: { item: ToastItem; onDismiss: (id: string) => void }) {
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    const exitTimer = setTimeout(() => setExiting(true), 4600);
    const removeTimer = setTimeout(() => onDismiss(item.id), 5000);
    return () => {
      clearTimeout(exitTimer);
      clearTimeout(removeTimer);
    };
  }, [item.id, onDismiss]);

  return (
    <div
      className={`${
        exiting ? "toast-exit" : "toast-enter"
      } pointer-events-auto w-80 overflow-hidden rounded-sm border border-olive/30 bg-paper shadow-[0_10px_30px_-12px_rgba(26,24,22,0.25)]`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-start gap-3 px-4 py-3">
        <span className="mt-[5px] inline-block h-2 w-2 flex-none rounded-full bg-olive" />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-display text-sm font-semibold capitalize tracking-tight text-ink">
              {item.name}
            </span>
            <span className="text-[9px] font-medium uppercase tracking-caps text-olive">done</span>
          </div>
          <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-subink">
            {item.task || "Finished research task."}
          </p>
        </div>
      </div>
      <div className="toast-drain h-0.5 bg-olive/70" />
    </div>
  );
}

export function ToastStack({
  items,
  onDismiss,
}: {
  items: ToastItem[];
  onDismiss: (id: string) => void;
}) {
  return (
    <div className="pointer-events-none fixed right-6 top-6 z-50 flex flex-col gap-2.5">
      {items.map((item) => (
        <Toast key={item.id} item={item} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
