export type SSEFrame = { event: string; data: unknown };

// SSE spec (HTML Living Standard §9.2) treats \r\n, \r, and \n as newlines.
const FRAME_SEP = /\r\n\r\n|\r\r|\n\n/;
const LINE_SEP = /\r\n|\r|\n/;

export function consumeFrames(buffer: string): SSEFrame[] {
  const frames: SSEFrame[] = [];
  const parts = buffer.split(FRAME_SEP);
  // last part may be incomplete — only parse all but the last
  for (let i = 0; i < parts.length - 1; i++) {
    const block = parts[i];
    let event = "message";
    let dataStr = "";
    for (const line of block.split(LINE_SEP)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) {
        const value = line.slice(5).trim();
        dataStr = dataStr ? dataStr + "\n" + value : value;
      }
    }
    if (dataStr) {
      try {
        frames.push({ event, data: JSON.parse(dataStr) });
      } catch {
        frames.push({ event, data: dataStr });
      }
    }
  }
  return frames;
}

export function leftoverAfterFrames(buffer: string): string {
  const parts = buffer.split(FRAME_SEP);
  return parts[parts.length - 1];
}
