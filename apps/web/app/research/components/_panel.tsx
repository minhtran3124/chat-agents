/**
 * Shared sidebar-section atoms. One visual language, four call sites.
 * Changing the look of a panel header here updates it everywhere.
 */

export function SectionHeader({ title, count }: { title: string; count?: string | null }) {
  return (
    <div className="mb-4 flex items-center justify-between">
      <h2 className="font-mono text-[10px] font-semibold uppercase tracking-caps text-ink-muted">
        {title}
      </h2>
      {count && <span className="font-mono text-[10px] tabular-nums text-ink-dim">{count}</span>}
    </div>
  );
}

export function EmptyHint({ children }: { children: React.ReactNode }) {
  return <p className="text-sm italic leading-snug text-ink-dim">{children}</p>;
}

/**
 * A single quiet card used for researchers, reflections, and similar list rows.
 * surface tint + soft rule, a little breathing room inside.
 */
export function PanelCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <li
      className={`animate-fade-in-up rounded-lg border border-hairline-soft bg-surface px-3.5 py-3 text-sm transition hover:border-hairline ${className}`}
    >
      {children}
    </li>
  );
}

type PillTone = "neutral" | "accent" | "success" | "warn" | "danger";

const PILL_TONES: Record<PillTone, string> = {
  neutral: "border-hairline bg-canvas text-ink-muted",
  accent: "border-accent/25 bg-accent/8 text-accent-deep",
  success: "border-success/25 bg-success/8 text-success",
  warn: "border-warn/25 bg-warn/8 text-warn",
  danger: "border-danger/25 bg-danger/10 text-danger",
};

/**
 * Small rounded-full badge. Mirrors the tag style on the LangChain blog.
 */
export function Pill({
  tone = "neutral",
  children,
  className = "",
}: {
  tone?: PillTone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-caps ${PILL_TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
