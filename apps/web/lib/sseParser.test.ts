import { describe, expect, it } from "vitest";
import { consumeFrames, leftoverAfterFrames } from "./sseParser";

describe("sseParser", () => {
  it("parses a single complete frame", () => {
    const buf = 'event: foo\ndata: {"x":1}\n\n';
    expect(consumeFrames(buf)).toEqual([{ event: "foo", data: { x: 1 } }]);
  });

  it("returns leftover for incomplete frame", () => {
    const buf = 'event: foo\ndata: {"x":1}\n\nevent: bar\ndata: ';
    const frames = consumeFrames(buf);
    expect(frames).toHaveLength(1);
    expect(leftoverAfterFrames(buf)).toBe("event: bar\ndata: ");
  });

  it("handles multi-line data", () => {
    const buf = 'event: r\ndata: {"a":1}\n\nevent: r\ndata: {"a":2}\n\n';
    expect(consumeFrames(buf)).toHaveLength(2);
  });
});
