import assert from "node:assert/strict";
import { test } from "node:test";

import { unmatchedMarkers } from "../lib/citations.ts";
import { QUICK_PARAGRAPHS, REPORT_POINTS, SOURCES } from "./fixtures.ts";

test("every marker in the canned answers has a source card", () => {
  for (const texts of [QUICK_PARAGRAPHS.en, QUICK_PARAGRAPHS.es, REPORT_POINTS.en, REPORT_POINTS.es]) {
    assert.deepEqual(unmatchedMarkers(texts, SOURCES), []);
  }
});

test("Spanish versions keep every number from the English (the translate tool's check)", () => {
  const numbers = (text: string) => text.match(/\d+/g) ?? [];
  for (const [en, es] of [[QUICK_PARAGRAPHS.en, QUICK_PARAGRAPHS.es], [REPORT_POINTS.en, REPORT_POINTS.es]]) {
    en.forEach((text, i) => assert.deepEqual(numbers(es[i]), numbers(text)));
  }
});
