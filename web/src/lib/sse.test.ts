import assert from "node:assert/strict";
import { test } from "node:test";

import { readEvents, takeEvents } from "./sse.ts";

test("complete events are parsed and a partial one is kept for the next chunk", () => {
  const { events, rest } = takeEvents(
    'data: {"type":"step","id":"a","label":"A","status":"now"}\n\ndata: {"type":"source-fo',
  );
  assert.deepEqual(events, [{ type: "step", id: "a", label: "A", status: "now" }]);
  assert.equal(rest, 'data: {"type":"source-fo');
});

test("non-data lines are ignored and CRLF separators work", () => {
  const { events } = takeEvents('event: message\r\ndata: {"type":"step","id":"b","label":"B","status":"done"}\r\n\r\n');
  assert.equal(events.length, 1);
});

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

test("events split across network chunks arrive whole and in order", async () => {
  const seen = [];
  for await (const event of readEvents(streamOf(
    'data: {"type":"step","id":"a","label":"A","sta', 'tus":"now"}\n\n',
    'data: {"type":"step","id":"a","label":"A","status":"done"}',  // last event without "\n\n"
  ))) seen.push(event);
  assert.deepEqual(seen.map((e) => e.type === "step" && e.status), ["now", "done"]);
});

test("an error event from the API is thrown, not shown as an answer", async () => {
  await assert.rejects(async () => {
    for await (const _ of readEvents(streamOf('data: {"type":"error","message":"ToolError: search"}\n\n')));
  }, /ToolError: search/);
});
