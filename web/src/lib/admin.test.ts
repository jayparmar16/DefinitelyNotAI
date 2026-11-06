import assert from "node:assert/strict";
import { test } from "node:test";

import { allDeclined, status } from "./admin.ts";

test("tile status: on target, below target, no data yet", () => {
  assert.equal(status(0.93, 0.75, "higher"), "On target");
  assert.equal(status(0.6, 0.75, "higher"), "Below target");
  assert.equal(status(null, 0.75, "higher"), "No data yet");
  assert.equal(status(undefined, 1, "higher"), "No data yet");
});

test("100% cited is on target only at exactly 100%", () => {
  assert.equal(status(1, 1, "higher"), "On target");
  assert.equal(status(0.99, 1, "higher"), "Below target");
});

test("under one minute is on target; a minute or more is not", () => {
  assert.equal(status(17.4, 60, "lower"), "On target");
  assert.equal(status(60, 60, "lower"), "Below target");
  assert.equal(status(0, 60, "lower"), "On target");
});

test("unanswerable questions: all declined", () => {
  assert.equal(allDeclined("3 of 3"), "On target");
  assert.equal(allDeclined("2 of 3"), "Below target");
  assert.equal(allDeclined("0 of 0"), "No data yet");
  assert.equal(allDeclined(null), "No data yet");
});
