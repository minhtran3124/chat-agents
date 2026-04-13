import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function ReportView({ text }: { text: string }) {
  return (
    <div className="h-full overflow-auto p-4">
      <h3 className="mb-2 font-semibold">📄 Report</h3>
      {text ? (
        <article className="prose prose-sm max-w-none">
          <Markdown remarkPlugins={[remarkGfm]}>{text}</Markdown>
        </article>
      ) : (
        <div className="text-sm text-gray-400">—</div>
      )}
    </div>
  );
}
