import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Status = "idle" | "loading" | "streaming" | "done" | "error";
type Source = "stream" | "file" | "error" | null;

/**
 * Normalise agent output before handing it to react-markdown.
 *
 * Problems we fix:
 * 1. Agent preamble — short prose before the first heading ("Here is the
 *    final report…") gets stripped so the drop-cap lands on real content.
 * 2. Trailing ** / *** on heading lines — the agent sometimes leaves stray
 *    emphasis markers at the end of an h2/h3; remove them.
 * 3. *** as section dividers — react-markdown can misparse standalone ***
 *    as bold-italic delimiters instead of a thematic break, especially
 *    without blank lines.  Replace them with unambiguous --- separators.
 */
function sanitizeReport(text: string): string {
  let out = text
    .replace(/^[ \t]*\*{3,}[ \t]*$/gm, "---")
    .replace(/(^#{1,6} .+?)\s*\*{2,3}[ \t]*$/gm, "$1")
    .trim();

  const firstHeading = out.search(/^#{1,6} /m);
  if (firstHeading > 0) {
    const preamble = out.slice(0, firstHeading);
    const looksLikeCommentary = preamble.length < 300 && !/^[-*>]|\d+\./m.test(preamble);
    if (looksLikeCommentary) {
      out = out.slice(firstHeading).trim();
    }
  }

  return out;
}

export function ReportView({
  text,
  status = "idle",
  source = null,
}: {
  text: string;
  status?: Status;
  source?: Source;
}) {
  if (!text) {
    if (status === "loading") return <Preparing />;
    if (status === "streaming") return <Researching />;
    return <Welcome />;
  }

  const streaming = status === "streaming";
  const reconstructed = status === "done" && source === "file";
  const clean = sanitizeReport(text);

  return (
    <div className="mx-auto max-w-[720px] px-10 py-14">
      <div className="mb-8 flex items-center gap-3 border-b border-hairline pb-4">
        <span className="font-mono text-[10px] font-medium uppercase tracking-caps text-ink-dim">
          The brief
        </span>
        <span className="h-px flex-1 bg-hairline-soft" aria-hidden />
        {streaming && (
          <span className="inline-flex items-center gap-1.5 font-mono text-[10px] font-medium uppercase tracking-caps text-accent-deep">
            <span className="animate-soft-pulse h-1.5 w-1.5 rounded-full bg-accent" />
            writing
          </span>
        )}
        {status === "done" && !reconstructed && (
          <span className="font-mono text-[10px] font-medium uppercase tracking-caps text-success">
            ready
          </span>
        )}
        {reconstructed && (
          <span
            className="font-mono text-[10px] font-medium uppercase tracking-caps text-warn"
            title="The agent saved the report to a file instead of replying inline; the UI rebuilt it from draft.md."
          >
            rebuilt from notes
          </span>
        )}
      </div>
      {/* brief-streaming disables the drop-cap while output is mid-stream */}
      <article className={streaming ? "brief brief-streaming" : "brief"}>
        <Markdown remarkPlugins={[remarkGfm]}>{clean}</Markdown>
        {streaming && <span className="brief-cursor" aria-hidden />}
      </article>
    </div>
  );
}

const LOADING_STEPS = [
  "Parsing your question",
  "Summoning the planner",
  "Dispatching researchers",
  "Opening the virtual filesystem",
];

function Preparing() {
  return (
    <div className="mx-auto flex h-full max-w-2xl items-center px-10 py-12">
      <div className="w-full">
        <div className="bg-warn/8 mb-6 inline-flex items-center gap-2 rounded-full border border-warn/25 px-3 py-1 font-mono text-[10px] font-medium uppercase tracking-caps text-warn">
          <span className="flex gap-1" aria-hidden>
            <span className="animate-loading-dot h-1.5 w-1.5 rounded-full bg-warn" />
            <span
              className="animate-loading-dot h-1.5 w-1.5 rounded-full bg-warn"
              style={{ animationDelay: "0.18s" }}
            />
            <span
              className="animate-loading-dot h-1.5 w-1.5 rounded-full bg-warn"
              style={{ animationDelay: "0.36s" }}
            />
          </span>
          Preparing
        </div>

        <h2 className="font-display text-[52px] font-semibold leading-[1.05] tracking-tight text-ink">
          Warming up <span className="italic text-accent">the journal.</span>
        </h2>

        <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-ink-muted">
          Sketching a plan, summoning specialist researchers, and opening the virtual filesystem.
          The brief will begin streaming here in a moment.
        </p>

        <div className="mt-10 border-t border-hairline-soft pt-6">
          <div className="mb-4 font-mono text-[10px] font-medium uppercase tracking-caps text-ink-dim">
            Behind the scenes
          </div>
          <ul className="space-y-3 text-sm">
            {LOADING_STEPS.map((step, i) => (
              <li
                key={step}
                className="animate-fade-in-up flex items-center gap-3 text-ink-muted"
                style={{ animationDelay: `${i * 220}ms` }}
              >
                <span
                  className="animate-soft-pulse h-1.5 w-1.5 rounded-full bg-warn"
                  style={{ animationDelay: `${i * 220}ms` }}
                />
                <span className="font-medium text-ink/85">{step}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-10 space-y-2.5" aria-hidden>
          <SkeletonLine width="85%" />
          <SkeletonLine width="72%" />
          <SkeletonLine width="92%" />
          <SkeletonLine width="60%" />
        </div>
      </div>
    </div>
  );
}

function Researching() {
  return (
    <div className="mx-auto flex h-full max-w-2xl items-center px-10 py-12">
      <div className="w-full">
        <div className="bg-accent/8 mb-6 inline-flex items-center gap-2 rounded-full border border-accent/25 px-3 py-1 font-mono text-[10px] font-medium uppercase tracking-caps text-accent-deep">
          <span className="animate-soft-pulse h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
          Researching
        </div>

        <h2 className="font-display text-[52px] font-semibold leading-[1.05] tracking-tight text-ink">
          Researchers are <span className="italic text-accent">at work.</span>
        </h2>

        <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-ink-muted">
          Specialist researchers are digging in, saving notes as they find them. The brief will
          begin streaming here once they surface enough to write.
        </p>

        <div className="mt-10 space-y-2.5" aria-hidden>
          <SkeletonLine width="88%" />
          <SkeletonLine width="74%" />
          <SkeletonLine width="95%" />
          <SkeletonLine width="65%" />
          <SkeletonLine width="80%" />
        </div>
      </div>
    </div>
  );
}

function SkeletonLine({ width }: { width: string }) {
  return (
    <div className="animate-skeleton-shimmer h-2.5 rounded-sm bg-surface-2" style={{ width }} />
  );
}

function Welcome() {
  return (
    <div className="mx-auto flex h-full max-w-2xl items-center px-10 py-12">
      <div>
        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-hairline bg-canvas px-3 py-1 font-mono text-[10px] font-medium uppercase tracking-caps text-ink-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          Deep research, live
        </div>
        <h2 className="font-display text-[60px] font-semibold leading-[1.02] tracking-tight text-ink">
          What would you like <span className="italic text-accent">researched?</span>
        </h2>
        <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-ink-muted">
          Type a question above. You&rsquo;ll watch the journal sketch a plan, send specialist
          researchers to dig in, save notes as they find them, and write the brief here in real time
          &mdash; citations included.
        </p>
        <div className="mt-10 border-t border-hairline-soft pt-6">
          <div className="mb-4 font-mono text-[10px] font-medium uppercase tracking-caps text-ink-dim">
            Try asking
          </div>
          <ul className="space-y-2.5 font-display text-[17px] italic text-ink/90">
            <li className="flex gap-3">
              <span className="select-none text-accent">—</span>
              Compare LangGraph, AutoGen, and CrewAI for production multi-agent systems.
            </li>
            <li className="flex gap-3">
              <span className="select-none text-accent">—</span>
              What&rsquo;s the state of retrieval-augmented generation for enterprise search?
            </li>
            <li className="flex gap-3">
              <span className="select-none text-accent">—</span>
              How are major labs handling model evaluation and red-teaming in 2025?
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
