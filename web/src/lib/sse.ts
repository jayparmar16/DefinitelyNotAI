/** Server-sent events from the AskWRI API: turn a byte stream into AgentEvents as they arrive. */

import type { AgentEvent } from "./agent.ts";

/** An event the API sends when the run failed after the stream opened. */
export type ErrorEvent = { type: "error"; message: string };

/**
 * Split buffered text into complete events. Returns the events and the unfinished remainder
 * to prepend to the next chunk. Only "data:" lines are read; other SSE fields are ignored.
 */
export function takeEvents(buffer: string): { events: (AgentEvent | ErrorEvent)[]; rest: string } {
  const blocks = buffer.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? "";
  const events: (AgentEvent | ErrorEvent)[] = [];
  for (const block of blocks) {
    const data = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trim())
      .join("\n");
    if (data) events.push(JSON.parse(data));
  }
  return { events, rest };
}

/** Read a response body as AgentEvents; an "error" event from the API is thrown. */
export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<AgentEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const { events, rest } = takeEvents(done ? `${buffer}\n\n` : buffer);
    buffer = rest;
    for (const event of events) {
      if (event.type === "error") throw new Error(event.message);
      yield event;
    }
    if (done) return;
  }
}
