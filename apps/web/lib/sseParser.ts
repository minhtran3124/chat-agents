export type SSEFrame = { event: string; data: unknown };

export function consumeFrames(buffer: string): SSEFrame[] {
  const frames: SSEFrame[] = [];
  const parts = buffer.split("\n\n");
  // last part may be incomplete — only parse all but the last
  for (let i = 0; i < parts.length - 1; i++) {
    const block = parts[i];
    let event = "message";
    let dataStr = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
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
  const parts = buffer.split("\n\n");
  return parts[parts.length - 1];
}
