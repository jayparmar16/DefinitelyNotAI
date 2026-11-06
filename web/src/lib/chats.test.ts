import assert from "node:assert/strict";
import { test } from "node:test";

import type { Turn } from "../components/turn.ts";
import { upsertChat, whenLabel } from "./chats.ts";

function turn(question: string, status: Turn["status"] = "done"): Turn {
  return {
    id: question, question, mode: "quick", status, startedAt: 0, steps: [], found: [], outdated: [],
    answer: null, decline: null, error: null, translation: null,
  };
}

test("a chat is saved first, replacing its older copy, without turns still running", () => {
  let chats = upsertChat([], "s1", [turn("Heat in cities?")], 1);
  chats = upsertChat(chats, "s2", [turn("Air quality?")], 2);
  chats = upsertChat(chats, "s1", [turn("Heat in cities?"), turn("And Kigali?"), turn("…", "running")], 3);
  assert.deepEqual(chats.map((c) => c.sessionId), ["s1", "s2"]);
  assert.equal(chats[0].title, "Heat in cities?");
  assert.deepEqual(chats[0].turns.map((t) => t.question), ["Heat in cities?", "And Kigali?"]);
});

test("a chat with nothing finished isn't saved, and the list keeps the 12 newest", () => {
  assert.deepEqual(upsertChat([], "s", [turn("q", "running")], 1), []);
  let chats: ReturnType<typeof upsertChat> = [];
  for (let i = 0; i < 14; i++) chats = upsertChat(chats, `s${i}`, [turn(`q${i}`)], i);
  assert.equal(chats.length, 12);
  assert.equal(chats[0].sessionId, "s13");
});

test("opening or updating a chat keeps the list's order; a new question moves it to the top", () => {
  let chats = upsertChat([], "s1", [turn("Heat?")], 1);
  chats = upsertChat(chats, "s2", [turn("Air?")], 2);
  chats = upsertChat(chats, "s3", [turn("Water?")], 3);
  // Opening s1 saves its same turns again (and a translation changes one in place).
  chats = upsertChat(chats, "s1", [{ ...turn("Heat?"), error: "edited" }], 4);
  assert.deepEqual(chats.map((c) => c.sessionId), ["s3", "s2", "s1"]);
  assert.equal(chats[2].updatedAt, 1);
  assert.equal(chats[2].turns[0].error, "edited");
  chats = upsertChat(chats, "s1", [turn("Heat?"), turn("And Kigali?")], 5);
  assert.deepEqual(chats.map((c) => c.sessionId), ["s1", "s3", "s2"]);
  assert.equal(chats[0].updatedAt, 5);
});

test("times read naturally", () => {
  const now = 10 * 24 * 3600 * 1000;
  assert.equal(whenLabel(now - 20_000, now), "just now");
  assert.equal(whenLabel(now - 5 * 60_000, now), "5 min ago");
  assert.equal(whenLabel(now - 3 * 3600_000, now), "3 h ago");
});


test("a chat remembers the space it was asked in", () => {
  const turn = { id: "t", question: "Ocean finance?", mode: "quick", status: "done", startedAt: 1, steps: [], found: [] } as unknown as Parameters<typeof upsertChat>[2][number];
  const [chat] = upsertChat([], "s1", [turn], 10, null, "Ocean");
  assert.equal(chat.space, "Ocean");
  assert.equal(upsertChat([], "s2", [turn], 10)[0].space, null);
});


test("a named chat (a demo chat's use case) keeps its title when saved again", () => {
  let chats = upsertChat([], "s1", [turn("How do cities cool?")], 1);
  chats = [{ ...chats[0], title: "1 · Verified answer", named: true }];
  chats = upsertChat(chats, "s1", [turn("How do cities cool?")], 2);
  assert.equal(chats[0].title, "1 · Verified answer");
});
