import { FileRef } from "@/lib/types";

export function FileList({ files }: { files: FileRef[] }) {
  return (
    <section className="p-6">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-display text-base font-semibold tracking-tight">Notes &amp; sources</h2>
        {files.length > 0 && (
          <span className="text-xs tabular-nums text-subink">{files.length}</span>
        )}
      </div>
      {files.length === 0 ? (
        <p className="text-sm italic leading-snug text-subink/80">
          The notebook clips research sources and drafts here as they&rsquo;re saved.
        </p>
      ) : (
        <ul className="max-h-80 space-y-1.5 overflow-y-auto pr-1 font-mono text-xs">
          {files.map((f) => (
            <li key={f.path} title={`${f.path}\n\n${f.preview}`} className="flex items-start gap-2">
              <span className="mt-[3px] flex-none text-terracotta" aria-hidden>
                ▸
              </span>
              <span className="min-w-0 flex-1 truncate text-ink/80">{prettyName(f.path)}</span>
              <span className="flex-none tabular-nums text-subink">
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
