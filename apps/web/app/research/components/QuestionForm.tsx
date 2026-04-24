"use client";
import { useEffect, useRef, useState } from "react";

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
  const inputRef = useRef<HTMLInputElement>(null);

  // ⌘K / Ctrl+K focuses the input — a small power-user affordance.
  useEffect(() => {
    function onKeydown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKeydown);
    return () => window.removeEventListener("keydown", onKeydown);
  }, []);

  const buttonLabel = loading ? "Preparing" : disabled ? "Researching" : "Research";

  return (
    <form
      className="border-b border-hairline bg-canvas px-8 py-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) onSubmit(q.trim());
      }}
    >
      <label className="mb-2 flex items-center gap-2 font-mono text-[10px] font-medium uppercase tracking-caps text-ink-dim">
        <span className="h-px w-4 bg-ink-dim/40" aria-hidden />
        Your question
      </label>
      <div className="flex items-stretch gap-3">
        <div className="relative flex-1">
          <input
            ref={inputRef}
            className="w-full rounded-lg border border-hairline bg-canvas px-4 py-3 pr-20 text-[15px] text-ink placeholder:text-ink-dim focus:border-accent focus:shadow-focus focus:outline-none disabled:opacity-60"
            placeholder={PLACEHOLDER}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            disabled={disabled}
          />
          <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 items-center gap-0.5 rounded-md border border-hairline bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink-dim md:inline-flex">
            <span className="text-[11px]">⌘</span>K
          </kbd>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-lg bg-accent px-5 font-mono text-[11px] font-semibold uppercase tracking-caps text-white transition hover:bg-accent-deep focus:outline-none focus:ring-2 focus:ring-accent/40 disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-ink-dim"
          disabled={disabled || !q.trim()}
        >
          {loading && <ButtonSpinner />}
          {buttonLabel}
          {!loading && !disabled && (
            <span className="text-[13px] leading-none" aria-hidden>
              →
            </span>
          )}
        </button>
      </div>
    </form>
  );
}

function ButtonSpinner() {
  return (
    <svg className="animate-spin-slow h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" aria-hidden>
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
