import assert from "node:assert/strict";
import { test } from "node:test";

import type { Source } from "./agent.ts";
import { claimsMatrix } from "./matrix.ts";

const source = (marker: number, docId: string, title = docId.toUpperCase()) =>
  ({ marker, docId, title, year: 2015, pubType: "Report" }) as Source;

test("paragraphs become columns headed by their short themes", () => {
  const matrix = claimsMatrix(
    ["Tracking began in four countries [1][2].", "Budgets rarely label adaptation spending [3]."],
    [source(1, "a"), source(2, "b"), source(3, "a")],
    ["Tracking", "Budget labels"],
  )!;
  assert.deepEqual(matrix.columns.map((c) => c.label), ["Tracking", "Budget labels"]);
  assert.equal(matrix.columns[1].text, "Budgets rarely label adaptation spending.");
  assert.deepEqual(matrix.rows.map((r) => [r.title, r.meta]), [["A", "Report · 2015"], ["B", "Report · 2015"]]);
  assert.deepEqual(matrix.cells, [[true, true], [true, false]]);
});

test("without themes, or with one paragraph, columns are short numbered points", () => {
  const sources = [source(1, "a"), source(2, "b")];
  assert.deepEqual(claimsMatrix(["One [1].", "Two [2]."], sources)!.columns.map((c) => c.label), ["Point 1", "Point 2"]);
  const single = claimsMatrix(["Framing sentence. One [1]. Two [2]."], sources, ["Theme"])!;
  assert.deepEqual(single.columns.map((c) => c.label), ["Point 1", "Point 2"]);
});

test("the same report filed twice is one row", () => {
  const twice = [source(1, "x-2024", "Cities Driving Change"), source(2, "x-2025", "Cities driving change"), source(3, "y")];
  const matrix = claimsMatrix(["A [1].", "B [2][3]."], twice, ["A", "B"])!;
  assert.equal(matrix.rows.length, 2);
  assert.deepEqual(matrix.cells[0], [true, true]);
});

test("one report or one point gives no matrix", () => {
  assert.equal(claimsMatrix(["Only point [1]."], [source(1, "a"), source(2, "b")]), null);
  assert.equal(claimsMatrix(["One [1]. Two [2]."], [source(1, "a"), source(2, "a")]), null);
});
