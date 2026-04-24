import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ErrorView } from "./ErrorView";

afterEach(() => {
  cleanup();
});

describe("ErrorView", () => {
  it("renders warning (warn) variant for budget_exceeded", () => {
    const { container } = render(
      <ErrorView
        budgetExceeded={{
          tokens_used: 207_432,
          limit: 200_000,
          message: "Run stopped: token budget exceeded (207,432 / 200,000 tokens).",
        }}
        onReset={vi.fn()}
      />,
    );

    expect(screen.getByText(/token budget exceeded/i)).toBeTruthy();
    expect(screen.getByText(/207,432/)).toBeTruthy();
    // Progress bar present
    expect(container.querySelector("[data-testid='budget-progress']")).not.toBeNull();
    // No retry button for budget
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
    // New-research button always present
    expect(screen.getByRole("button", { name: /new research/i })).toBeTruthy();
    // Warn variant styling
    expect(container.querySelector(".border-warn\\/40")).not.toBeNull();
  });

  it("renders error (danger) variant with retry button when recoverable", () => {
    const onReset = vi.fn();
    render(
      <ErrorView
        error="Research timed out."
        reason="timeout"
        recoverable={true}
        onReset={onReset}
        onRetry={vi.fn()}
      />,
    );
    // Both the header (derived from reason="timeout") and body message render;
    // assert we see two separate timed-out strings.
    expect(screen.getAllByText(/research timed out/i)).toHaveLength(2);
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: /try again/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /new research/i })).toBeTruthy();
  });

  it("renders error variant without retry button when not recoverable", () => {
    render(
      <ErrorView
        error="Something failed."
        reason="internal"
        recoverable={false}
        onReset={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
    expect(screen.getByRole("button", { name: /new research/i })).toBeTruthy();
  });

  it("new-research button invokes onReset", () => {
    const onReset = vi.fn();
    const { getByRole } = render(
      <ErrorView error="x" reason="internal" recoverable={false} onReset={onReset} />,
    );
    (getByRole("button", { name: /new research/i }) as HTMLButtonElement).click();
    expect(onReset).toHaveBeenCalledOnce();
  });
});
