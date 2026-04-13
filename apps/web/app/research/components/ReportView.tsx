import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Status = "idle" | "loading" | "streaming" | "done" | "error";

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
    // 1. Normalise standalone *** / **** lines → --- (thematic break)
    //    Must run before the heading fix so we don't touch emphasis inside text.
    .replace(/^[ \t]*\*{3,}[ \t]*$/gm, "---")
    // 2. Remove stray trailing ** or *** at end of heading lines
    .replace(/(^#{1,6} .+?)\s*\*{2,3}[ \t]*$/gm, "$1")
    .trim();

  // 3. Strip short agent preamble that appears before the first heading.
  //    Only remove it when it looks like commentary (no list/quote markers,
  //    shorter than 300 chars) so we don't accidentally drop a text-only report.
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
}: {
  text: string;
  status?: Status;
}) {
  if (!text) return <Welcome />;

  const streaming = status === "streaming";
  const clean = sanitizeReport(text);

  return (
    <div className="mx-auto max-w-3xl px-10 py-14">
      <div className="mb-8 flex items-baseline gap-3 border-b border-rule pb-4">
        <span className="text-[10px] uppercase tracking-caps text-subink">The brief</span>
        {streaming && (
          <span className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-caps text-terracotta">
            <span className="animate-soft-pulse">●</span> writing
          </span>
        )}
        {status === "done" && (
          <span className="text-[10px] uppercase tracking-caps text-olive">ready</span>
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

function Welcome() {
  return (
    <div className="mx-auto flex h-full max-w-2xl items-center px-10 py-12">
      <div>
        <p className="mb-3 text-[10px] uppercase tracking-caps text-subink">Deep research, live</p>
        <h2 className="font-display text-5xl font-semibold leading-[1.05] tracking-tight text-ink">
          What would you like <span className="italic text-terracotta">researched?</span>
        </h2>
        <p className="mt-5 max-w-lg text-base leading-relaxed text-subink">
          Type a question above. You&rsquo;ll watch the notebook sketch a plan, send
          specialist researchers to dig in, save notes as they find them, and write
          the brief here in real time &mdash; citations included.
        </p>
        <div className="mt-10 border-t border-rule pt-5">
          <div className="mb-3 text-[10px] uppercase tracking-caps text-subink">Try asking</div>
          <ul className="space-y-2 font-display italic text-ink/85">
            <li className="flex gap-2">
              <span className="select-none text-terracotta">&mdash;</span>
              Compare LangGraph, AutoGen, and CrewAI for production multi-agent systems.
            </li>
            <li className="flex gap-2">
              <span className="select-none text-terracotta">&mdash;</span>
              What&rsquo;s the state of retrieval-augmented generation for enterprise search?
            </li>
            <li className="flex gap-2">
              <span className="select-none text-terracotta">&mdash;</span>
              How are major labs handling model evaluation and red-teaming in 2025?
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
