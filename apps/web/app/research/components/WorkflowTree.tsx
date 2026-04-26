"use client";
import { useState } from "react";
import * as Tooltip from "@radix-ui/react-tooltip";
import type { AgentRole, ToolCallNode } from "@/lib/types";
import type { WorkflowState } from "@/lib/useResearchStream";

type Props = {
  workflow: WorkflowState;
};

const ROLE_COLOR: Record<AgentRole, { dot: string; text: string; border: string }> = {
  main: { dot: "bg-accent", text: "text-accent-deep", border: "border-accent/30" },
  researcher: { dot: "bg-success", text: "text-success", border: "border-success/30" },
  critic: { dot: "bg-warn", text: "text-warn", border: "border-warn/30" },
};

export function WorkflowTree({ workflow }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  if (workflow.rootIds.length === 0) return null;

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <Tooltip.Provider delayDuration={250}>
      <section className="border-b border-hairline-soft px-8 py-6">
        <header className="mb-3 flex items-baseline gap-2">
          <h2 className="font-mono text-[10px] font-semibold uppercase tracking-caps text-ink-muted">
            Workflow
          </h2>
          <span className="font-mono text-[10px] text-ink-dim">
            {Object.keys(workflow.nodes).length} steps
          </span>
        </header>
        <ul className="space-y-px">
          {workflow.rootIds.map((id) => (
            <NodeRow
              key={id}
              id={id}
              nodes={workflow.nodes}
              depth={0}
              expanded={expanded}
              onToggle={toggle}
            />
          ))}
        </ul>
      </section>
    </Tooltip.Provider>
  );
}

function NodeRow({
  id,
  nodes,
  depth,
  expanded,
  onToggle,
}: {
  id: string;
  nodes: Record<string, ToolCallNode>;
  depth: number;
  expanded: Set<string>;
  onToggle: (id: string) => void;
}) {
  const node = nodes[id];
  if (!node) return null;
  const isOpen = expanded.has(id);
  return (
    <>
      <li>
        <ToolRow node={node} depth={depth} isOpen={isOpen} onToggle={() => onToggle(id)} />
      </li>
      {isOpen && (
        <li>
          <ExpandedDetails node={node} depth={depth} />
        </li>
      )}
      {node.childIds.map((cid) => (
        <NodeRow
          key={cid}
          id={cid}
          nodes={nodes}
          depth={depth + 1}
          expanded={expanded}
          onToggle={onToggle}
        />
      ))}
      {node.files.map((path) => (
        <li key={path}>
          <FileRow path={path} depth={depth + 1} />
        </li>
      ))}
    </>
  );
}

function ToolRow({
  node,
  depth,
  isOpen,
  onToggle,
}: {
  node: ToolCallNode;
  depth: number;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const role = ROLE_COLOR[node.role];
  const isSlow = (node.durationMs ?? 0) > 5000;
  const isError = node.status === "error";
  const accentBorder = isError
    ? "border-danger/40"
    : isSlow && node.status !== "running"
      ? "border-warn/40"
      : "border-transparent";

  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={isOpen}
          className={`group flex w-full items-center gap-2 rounded-md border-l-2 ${accentBorder} bg-transparent py-1 pr-2 text-left transition hover:bg-surface-2/60 focus:outline-none focus:ring-2 focus:ring-accent/30`}
          style={{ paddingLeft: depth * 16 + 8 }}
          aria-label={`${node.role} called ${node.toolName}`}
        >
          <span
            aria-hidden
            className={`flex-shrink-0 font-mono text-[9px] text-ink-dim transition-transform ${isOpen ? "rotate-90" : ""}`}
          >
            ▸
          </span>
          <span
            aria-hidden
            className={`h-1.5 w-1.5 flex-shrink-0 rounded-full ${role.dot} ${node.status === "running" ? "animate-soft-pulse" : ""}`}
          />
          <span
            className={`font-mono text-[9px] font-semibold uppercase tracking-caps ${role.text}`}
          >
            {node.role}
          </span>
          <span className="truncate font-mono text-[12px] text-ink">{node.toolName}</span>
          {node.argsPreview && (
            <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-ink-dim">
              {node.argsPreview}
            </span>
          )}
          <StatusGlyph status={node.status} />
          {node.durationMs !== undefined && (
            <span
              className={`flex-shrink-0 font-mono text-[10px] tabular-nums ${isSlow ? "text-warn" : "text-ink-dim"}`}
            >
              {formatDuration(node.durationMs)}
            </span>
          )}
        </button>
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side="bottom"
          align="start"
          sideOffset={4}
          className="data-[state=delayed-open]:animate-in data-[state=closed]:animate-out z-50 max-w-[480px] rounded-md border border-hairline bg-canvas px-3 py-2 shadow-toast"
        >
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span
                className={`font-mono text-[9px] font-semibold uppercase tracking-caps ${role.text}`}
              >
                {node.role}
              </span>
              <span className="font-mono text-[11px] font-semibold text-ink">{node.toolName}</span>
            </div>
            {node.argsPreview && (
              <pre className="whitespace-pre-wrap break-words font-mono text-[11px] text-ink-muted">
                {node.argsPreview}
              </pre>
            )}
            {node.resultPreview && (
              <>
                <div className="font-mono text-[9px] uppercase tracking-caps text-ink-dim">
                  result
                </div>
                <pre className="whitespace-pre-wrap break-words font-mono text-[11px] text-ink-muted">
                  {node.resultPreview}
                </pre>
              </>
            )}
          </div>
          <Tooltip.Arrow className="fill-canvas stroke-hairline" />
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

function ExpandedDetails({ node, depth }: { node: ToolCallNode; depth: number }) {
  const role = ROLE_COLOR[node.role];
  let argsBody = node.argsPreview;
  try {
    if (argsBody) argsBody = JSON.stringify(JSON.parse(argsBody), null, 2);
  } catch {
    // Leave argsPreview as-is when it isn't valid JSON.
  }
  return (
    <div
      className="my-1 rounded-md border border-hairline-soft bg-surface/60 px-3 py-2"
      style={{ marginLeft: depth * 16 + 24 }}
    >
      <div className="mb-1.5 flex items-center gap-2">
        <span className={`font-mono text-[9px] font-semibold uppercase tracking-caps ${role.text}`}>
          {node.role}
        </span>
        <span className="font-mono text-[11px] font-semibold text-ink">{node.toolName}</span>
        {node.durationMs !== undefined && (
          <span className="font-mono text-[10px] tabular-nums text-ink-dim">
            · {formatDuration(node.durationMs)}
          </span>
        )}
      </div>
      {argsBody && (
        <DetailBlock label="args">
          <pre className="whitespace-pre-wrap break-words font-mono text-[11px] text-ink-muted">
            {argsBody}
          </pre>
        </DetailBlock>
      )}
      {node.resultPreview && (
        <DetailBlock label="result">
          <pre className="whitespace-pre-wrap break-words font-mono text-[11px] text-ink-muted">
            {node.resultPreview}
          </pre>
        </DetailBlock>
      )}
      {node.files.length > 0 && (
        <DetailBlock label={`wrote ${node.files.length} file${node.files.length > 1 ? "s" : ""}`}>
          <ul className="space-y-0.5">
            {node.files.map((path) => (
              <li key={path} className="font-mono text-[11px] text-ink-muted">
                {path}
              </li>
            ))}
          </ul>
        </DetailBlock>
      )}
    </div>
  );
}

function DetailBlock({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mt-1.5 first:mt-0">
      <div className="mb-1 font-mono text-[9px] uppercase tracking-caps text-ink-dim">{label}</div>
      {children}
    </div>
  );
}

function FileRow({ path, depth }: { path: string; depth: number }) {
  return (
    <div className="flex items-center gap-2 py-0.5 pr-2" style={{ paddingLeft: depth * 16 + 8 }}>
      <span aria-hidden className="font-mono text-[10px] text-ink-dim">
        ↳
      </span>
      <span className="font-mono text-[9px] uppercase tracking-caps text-ink-dim">wrote</span>
      <span className="truncate font-mono text-[11px] text-ink-muted">{path}</span>
    </div>
  );
}

function StatusGlyph({ status }: { status: ToolCallNode["status"] }) {
  if (status === "running") {
    return (
      <span
        aria-label="running"
        className="animate-soft-pulse h-1 w-1 flex-shrink-0 rounded-full bg-accent"
      />
    );
  }
  if (status === "error") {
    return (
      <span aria-label="error" className="font-mono text-[10px] font-semibold text-danger">
        ✕
      </span>
    );
  }
  return (
    <span aria-label="ok" className="font-mono text-[10px] text-success">
      ✓
    </span>
  );
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}
