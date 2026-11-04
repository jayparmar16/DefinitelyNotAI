import assert from "node:assert/strict";
import { test } from "node:test";

import { findPassage, highlightRanges, normalize, pageStream } from "./highlight.ts";

test("normalising ignores whitespace, case, hyphens, ligatures and quote styles", () => {
  assert.equal(normalize("Cities’ ﬁnancing — Long-term\n  PLANS"), normalize("cities' financing long term plans"));
  assert.equal(normalize("181 of 394"), "181of394");
});

test("a passage split across spans with a hyphenated line break is found whole", () => {
  const spans = [
    "Header text that is not cited. ",
    "Nearly half of the cities stud-",
    "ied (181 of 394) did not meet",
    " the 2030 standards in 2024.",
    "Footer.",
  ];
  const ranges = highlightRanges(spans, "Nearly half of the cities studied (181 of 394) did not meet the 2030 standards in 2024.");
  assert.deepEqual(
    ranges.map((r) => r.span),
    [1, 2, 3],
  );
  assert.deepEqual(ranges[0], { span: 1, start: 0, end: 30 }); // through the "stud" before the hyphen
  assert.equal(spans[3].slice(ranges[2].start, ranges[2].end), "the 2030 standards in 2024");
});

test("a passage that runs on to the next page highlights the part on this page", () => {
  const onPage = "Member States must consider the indicative list of pollution abatement measures in Annex VIII";
  const passage = `${onPage} of the new AAQD in their air quality planning and provide information on measures.`;
  const { text } = pageStream(["Some other text. ", onPage]);
  const runs = findPassage(text, passage);
  assert.equal(runs.length, 1);
  const [start, end] = runs[0];
  assert.ok(end - start >= normalize(onPage).length - 32, "most of the on-page part is matched");
});

test("short or absent passages highlight nothing rather than something wrong", () => {
  assert.deepEqual(highlightRanges(["The cities studied."], "cities"), []);
  assert.deepEqual(highlightRanges(["Completely different page text about forests and water."], "Air pollution remains Europe's number one environmental health risk."), []);
});
