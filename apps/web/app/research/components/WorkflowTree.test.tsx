import { describe, expect, it } from "vitest";
import { fireEvent, render } from "@testing-library/react";
import { WorkflowTree } from "./WorkflowTree";
import type { ToolCallNode } from "@/lib/types";
import type { WorkflowState } from "@/lib/useResearchStream";

function makeNode(partial: Partial<ToolCallNode> & { id: string }): ToolCallNode {
  return {
    role: "main",
    toolName: "internet_search",
    argsPreview: "",
    status: "running",
    parentId: null,
    childIds: [],
    files: [],
    startedAt: 0,
    ...partial,
  };
}

function workflow(state: Partial<WorkflowState>): WorkflowState {
  return {
    nodes: {},
    rootIds: [],
    taskStack: [],
    lastNonTaskCallId: null,
    ...state,
  };
}

describe("WorkflowTree", () => {
  it("renders nothing when there are no nodes", () => {
    const { container } = render(<WorkflowTree workflow={workflow({})} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders root tool calls with name and role label", () => {
    const root = makeNode({ id: "c1", toolName: "internet_search", role: "main" });
    const { getByText } = render(
      <WorkflowTree workflow={workflow({ nodes: { c1: root }, rootIds: ["c1"] })} />,
    );
    expect(getByText("internet_search")).toBeTruthy();
    expect(getByText("main")).toBeTruthy();
  });

  it("renders child tool calls nested under their parent", () => {
    const parent = makeNode({
      id: "task1",
      toolName: "task",
      role: "main",
      childIds: ["child1"],
    });
    const child = makeNode({
      id: "child1",
      toolName: "internet_search",
      role: "researcher",
      parentId: "task1",
    });
    const { getByText } = render(
      <WorkflowTree
        workflow={workflow({
          nodes: { task1: parent, child1: child },
          rootIds: ["task1"],
        })}
      />,
    );
    expect(getByText("task")).toBeTruthy();
    expect(getByText("internet_search")).toBeTruthy();
    expect(getByText("researcher")).toBeTruthy();
  });

  it("renders files under the owning tool node", () => {
    const owner = makeNode({
      id: "search1",
      toolName: "internet_search",
      files: ["/r/searches/foo.md"],
    });
    const { getByText } = render(
      <WorkflowTree workflow={workflow({ nodes: { search1: owner }, rootIds: ["search1"] })} />,
    );
    expect(getByText("/r/searches/foo.md")).toBeTruthy();
  });

  it("shows duration once a tool completes", () => {
    const done = makeNode({
      id: "c1",
      toolName: "read_file",
      status: "ok",
      durationMs: 320,
    });
    const { getByText } = render(
      <WorkflowTree workflow={workflow({ nodes: { c1: done }, rootIds: ["c1"] })} />,
    );
    expect(getByText("320ms")).toBeTruthy();
  });

  it("click on a row toggles inline expanded details", () => {
    const node = makeNode({
      id: "c1",
      toolName: "internet_search",
      role: "main",
      argsPreview: '{"query":"deep research"}',
      resultPreview: "found 5 sources",
      status: "ok",
      durationMs: 1400,
    });
    const { getAllByRole, queryByText, getByText } = render(
      <WorkflowTree workflow={workflow({ nodes: { c1: node }, rootIds: ["c1"] })} />,
    );
    expect(queryByText("args")).toBeNull();
    fireEvent.click(getAllByRole("button")[0]);
    expect(getByText("args")).toBeTruthy();
    expect(getByText("result")).toBeTruthy();
    expect(getByText("found 5 sources")).toBeTruthy();
    fireEvent.click(getAllByRole("button")[0]);
    expect(queryByText("args")).toBeNull();
  });

  it("formats durations over 1 second with one decimal place", () => {
    const slow = makeNode({
      id: "c1",
      toolName: "task",
      status: "ok",
      durationMs: 5300,
    });
    const { getByText } = render(
      <WorkflowTree workflow={workflow({ nodes: { c1: slow }, rootIds: ["c1"] })} />,
    );
    expect(getByText("5.3s")).toBeTruthy();
  });
});
