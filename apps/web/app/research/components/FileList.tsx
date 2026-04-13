import { FileRef } from "@/lib/types";

export function FileList({ files }: { files: FileRef[] }) {
  if (files.length === 0) return null;
  return (
    <div className="border-b p-3">
      <h3 className="mb-2 font-semibold">
        📁 Files (vFS){" "}
        <span className="text-xs font-normal text-gray-400">({files.length})</span>
      </h3>
      <ul className="max-h-80 space-y-1 overflow-y-auto pr-1 font-mono text-sm">
        {files.map((f) => (
          <li key={f.path} title={f.preview}>
            {f.path} <span className="text-gray-400">({f.size_tokens.toLocaleString()} tok)</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
