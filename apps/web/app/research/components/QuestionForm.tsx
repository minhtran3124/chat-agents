"use client";
import { useState } from "react";

const PLACEHOLDER =
  "Compare LangGraph, AutoGen, and CrewAI for production multi-agent systems in 2025…";

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
      className="border-b border-rule bg-paper/60 px-8 py-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) onSubmit(q.trim());
      }}
    >
      <label className="block text-[10px] font-medium uppercase tracking-caps text-subink">
        Your question
      </label>
      <div className="mt-2 flex items-stretch gap-3">
        <input
          className="flex-1 rounded-sm border border-rule bg-paper px-4 py-3 text-base text-ink placeholder:text-subink/60 focus:border-terracotta focus:outline-none focus:ring-1 focus:ring-terracotta/40 disabled:opacity-60"
          placeholder={PLACEHOLDER}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          disabled={disabled}
        />
        <button
          className="rounded-sm bg-ink px-6 font-display text-base font-medium text-cream transition hover:bg-terracotta focus:outline-none focus:ring-2 focus:ring-terracotta/40 disabled:cursor-not-allowed disabled:bg-subink/70 disabled:opacity-80"
          disabled={disabled || !q.trim()}
        >
          {disabled ? "Researching…" : "Begin"}
        </button>
      </div>
    </form>
  );
}
