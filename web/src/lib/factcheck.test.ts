import assert from "node:assert/strict";
import { test } from "node:test";

import type { CheckedClaim, FactCheck } from "./agent.ts";
import { annotate, countsLine, factCheckMarkdown } from "./factcheck.ts";
import { noteText } from "./factcheck.ts";

function claim(quote: string, verdict: CheckedClaim["verdict"] = "supported"): CheckedClaim {
  return { quote, claim: quote, verdict, markers: verdict === "not_found" ? [] : [1], correction: "", note: "" };
}

test("claims are found in the draft in order, and the rest of the text is kept", () => {
  const draft = "Dear partner. WRI found 281 of 394 cities missed it. Air pollution is the top risk. Thanks!";
  const segments = annotate(draft, [claim("air pollution is the top risk"), claim("WRI found 281 of 394 cities missed it", "contradicted")]);
  assert.equal(segments.map((s) => s.text).join(""), draft);
  assert.deepEqual(segments.map((s) => s.claim), [null, 1, null, 0, null]);
});

test("a quote that isn't in the draft, or overlaps another, stays unhighlighted", () => {
  const segments = annotate("Cities are warming fast.", [claim("Cities are warming"), claim("warming fast"), claim("not in it")]);
  assert.deepEqual(segments, [{ text: "Cities are warming", claim: 0 }, { text: " fast.", claim: null }]);
});

test("the report counts verdicts and keeps corrections", () => {
  const check: FactCheck = {
    draft: "",
    claims: [{ ...claim("281 cities", "contradicted"), correction: "181 of 394 cities" }, claim("x", "not_found")],
    counts: { supported: 0, contradicted: 1, outdated: 0, not_found: 1 },
    sources: [],
    elapsedSeconds: 3,
  };
  assert.equal(countsLine(check), "2 claims: 1 contradicted · 1 not found");
  const markdown = factCheckMarkdown(check);
  assert.match(markdown, /- \*\*Contradicted\*\*: 281 cities \[1\]\n {2}- Suggested wording: 181 of 394 cities/);
  assert.match(markdown, /- \*\*Not found\*\*: x\n/);
});


test("a note that opens with a source number reads as 'Source [n] …'", () => {
  assert.equal(noteText("[1] gives $9.4 billion, not $94 billion."), "Source [1] gives $9.4 billion, not $94 billion.");
  assert.equal(noteText("WRI says [2] instead."), "WRI says [2] instead.");
});
