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

  it("parses CRLF-terminated frames (sse-starlette default)", () => {
    const buf = 'event: foo\r\ndata: {"x":1}\r\n\r\n';
    expect(consumeFrames(buf)).toEqual([{ event: "foo", data: { x: 1 } }]);
  });

  it("returns leftover for incomplete CRLF frame", () => {
    const buf = 'event: foo\r\ndata: {"x":1}\r\n\r\nevent: bar\r\ndata: ';
    expect(consumeFrames(buf)).toHaveLength(1);
    expect(leftoverAfterFrames(buf)).toBe("event: bar\r\ndata: ");
  });

  it("parses mixed CRLF and LF frames in one buffer", () => {
    const buf = 'event: a\r\ndata: {"n":1}\r\n\r\nevent: b\ndata: {"n":2}\n\n';
    const frames = consumeFrames(buf);
    expect(frames).toEqual([
      { event: "a", data: { n: 1 } },
      { event: "b", data: { n: 2 } },
    ]);
  });

  it("joins multiple data: lines in one frame with \\n (per SSE spec)", () => {
    const buf = "event: x\ndata: line1\ndata: line2\n\n";
    expect(consumeFrames(buf)).toEqual([{ event: "x", data: "line1\nline2" }]);
  });
});
