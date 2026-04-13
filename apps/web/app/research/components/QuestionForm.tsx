"use client";
import { useState } from "react";

export function QuestionForm({
  onSubmit,
  disabled,
}: {
  onSubmit: (q: string) => void;
  disabled: boolean;
}) {
  const [q, setQ] = useState("");
  return (
    <form
      className="flex gap-2 border-b p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) onSubmit(q.trim());
      }}
    >
      <input
        className="flex-1 rounded border px-3 py-2"
        placeholder="Ask a research question..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
        disabled={disabled}
      />
      <button
        className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
        disabled={disabled || !q.trim()}
      >
        Start
      </button>
    </form>
  );
}
