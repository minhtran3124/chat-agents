import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { ReportView } from "./ReportView";

describe("ReportView", () => {
  it("renders bold markdown as <strong>", () => {
    const { container } = render(<ReportView text="hello **world**" />);
    const strong = container.querySelector("strong");
    expect(strong?.textContent).toBe("world");
  });

  it("renders GFM tables (remark-gfm active)", () => {
    const md = "| a | b |\n| - | - |\n| 1 | 2 |";
    const { container } = render(<ReportView text={md} />);
    expect(container.querySelector("table")).not.toBeNull();
    expect(container.querySelectorAll("td")).toHaveLength(2);
  });

  it("renders welcome card when text is empty", () => {
    const { getByText } = render(<ReportView text="" />);
    expect(getByText(/what would you like/i)).toBeTruthy();
  });
});
