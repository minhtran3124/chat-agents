"use client";
import { useState } from "react";

const PLACEHOLDER =
  "Compare LangGraph, AutoGen, and CrewAI for production multi-agent systems in 2025…";

export function QuestionForm({
  onSubmit,
  disabled,
  loading = false,
}: {
  onSubmit: (q: string) => void;
  disabled: boolean;
  loading?: boolean;
}) {
  const [q, setQ] = useState("");

  const buttonLabel = loading ? "Preparing…" : disabled ? "Researching…" : "Begin";

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
          className="inline-flex items-center gap-2 rounded-sm bg-ink px-6 font-display text-base font-medium text-cream transition hover:bg-terracotta focus:outline-none focus:ring-2 focus:ring-terracotta/40 disabled:cursor-not-allowed disabled:bg-subink/70 disabled:opacity-80"
          disabled={disabled || !q.trim()}
        >
          {loading && <ButtonSpinner />}
          {buttonLabel}
        </button>
      </div>
    </form>
  );
}

function ButtonSpinner() {
  return (
    <svg className="animate-spin-slow h-4 w-4" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.3" />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
