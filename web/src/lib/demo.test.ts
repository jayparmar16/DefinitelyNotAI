import assert from "node:assert/strict";
import { test } from "node:test";

import type { AgentEvent } from "./agent.ts";
import { demoChats } from "./demo.ts";

const answer = { type: "answer", answer: { paragraphs: ["Roofs cool [1]."], sources: [] } } as unknown as AgentEvent;

test("recorded chats become named, finished chats in the recorded order", () => {
  const chats = demoChats(
    [
      { title: "1 · Verified", space: null, sessionId: "a", question: "How do cities cool?", mode: "quick", events: [{ type: "step", id: "draft", label: "Drafting", status: "done" }, answer] },
      { title: "Ocean 2025", space: "Ocean", sessionId: "b", question: "Ocean 2025?", mode: "quick", events: [answer] },
    ],
    10_000,
  );
  assert.deepEqual(chats.map((c) => [c.title, c.named, c.space]), [["1 · Verified", true, null], ["Ocean 2025", true, "Ocean"]]);
  assert.ok(chats[0].updatedAt > chats[1].updatedAt);
  const turn = chats[0].turns[0];
  assert.equal(turn.status, "done");
  assert.equal(turn.answer?.paragraphs[0], "Roofs cool [1].");
  assert.equal(turn.steps.length, 1);
  assert.equal(chats[1].turns[0].space, "Ocean");
});
