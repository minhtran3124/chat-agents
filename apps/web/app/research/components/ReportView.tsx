export function ReportView({ text }: { text: string }) {
  return (
    <div className="h-full overflow-auto p-4">
      <h3 className="mb-2 font-semibold">📄 Report</h3>
      <pre className="whitespace-pre-wrap font-sans text-sm">{text || "—"}</pre>
    </div>
  );
}
