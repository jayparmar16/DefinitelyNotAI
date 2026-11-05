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
      { title: "Dossier", space: null, sessionId: "c", question: "Adaptation finance", mode: "deep", format: "dossier", events: [answer] },
    ],
    10_000,
  );
  assert.deepEqual(chats.map((c) => [c.title, c.named, c.space]), [["1 · Verified", true, null], ["Ocean 2025", true, "Ocean"], ["Dossier", true, null]]);
  assert.ok(chats[0].updatedAt > chats[1].updatedAt);
  const turn = chats[0].turns[0];
  assert.equal(turn.status, "done");
  assert.equal(turn.answer?.paragraphs[0], "Roofs cool [1].");
  assert.equal(turn.steps.length, 1);
  assert.equal(chats[1].turns[0].space, "Ocean");
  assert.equal(chats[2].turns[0].format, "dossier"); // reopening it restores Topic dossier
  assert.equal(chats[0].turns[0].format, undefined);
});


test("a story chat keeps its questions in order, each with its own report type", () => {
  const [story] = demoChats(
    [{
      title: "Story", space: null, sessionId: "s", question: "", mode: "quick", events: [],
      turns: [
        { question: "How are data centers affecting demand?", mode: "quick", events: [answer] },
        { question: "Data centers and the grid", mode: "deep", format: "issue-brief", events: [answer] },
        { question: "A draft to check", mode: "factcheck", events: [{ type: "factcheck", factcheck: { claims: [] } } as unknown as AgentEvent] },
      ],
    }],
    1,
  );
  assert.deepEqual(story.turns.map((t) => [t.mode, t.format ?? null, t.status]), [["quick", null, "done"], ["deep", "issue-brief", "done"], ["factcheck", null, "done"]]);
  assert.equal(new Set(story.turns.map((t) => t.id)).size, 3);
});


test("a recorded chat keeps the filters it was asked with", () => {
  const [chat] = demoChats(
    [{ title: "Filters", space: null, sessionId: "f", question: "Cities?", mode: "quick", filters: { region: "Sub-Saharan Africa" }, events: [answer] }],
    1,
  );
  assert.deepEqual(chat.turns[0].filters, { region: "Sub-Saharan Africa" });
});
