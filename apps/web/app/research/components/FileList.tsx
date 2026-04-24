import { FileRef } from "@/lib/types";
import { SectionHeader, EmptyHint } from "./_panel";

export function FileList({ files }: { files: FileRef[] }) {
  return (
    <section className="p-6">
      <SectionHeader title="Notes & sources" count={files.length > 0 ? `${files.length}` : null} />
      {files.length === 0 ? (
        <EmptyHint>
          The journal clips research sources and drafts here as they&rsquo;re saved.
        </EmptyHint>
      ) : (
        <ul className="scrollbar-quiet max-h-80 space-y-1 overflow-y-auto pr-1 font-mono text-xs">
          {files.map((f) => (
            <li
              key={f.path}
              title={`${f.path}\n\n${f.preview}`}
              className="group flex items-start gap-2 rounded px-1.5 py-1 hover:bg-surface-2"
            >
              <span
                className="mt-[3px] flex-none text-accent/70 group-hover:text-accent"
                aria-hidden
              >
                ›
              </span>
              <span className="min-w-0 flex-1 truncate text-ink/85">{prettyName(f.path)}</span>
              <span className="flex-none tabular-nums text-ink-dim">
                {f.size_tokens.toLocaleString()}t
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function prettyName(path: string): string {
  const stripped = path.replace(/^\//, "").replace(/^(deep_agents|large_tool_results)\//, "");
  return stripped.length > 48 ? "…" + stripped.slice(-45) : stripped;
}
