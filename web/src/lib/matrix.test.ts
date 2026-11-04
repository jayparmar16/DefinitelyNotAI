import assert from "node:assert/strict";
import { test } from "node:test";

import type { Source } from "./agent.ts";
import { claimsMatrix } from "./matrix.ts";

const source = (marker: number, docId: string) => ({ marker, docId, title: docId.toUpperCase(), year: 2015 }) as Source;

test("the matrix marks which report backs which point of the answer", () => {
  const matrix = claimsMatrix(
    ["Tracking began in four countries [1][2]. Budgets rarely label adaptation spending [3].", "Framing sentence."],
    [source(1, "a"), source(2, "b"), source(3, "a")],
  )!;
  assert.deepEqual(matrix.columns.map((c) => c.label), ["Tracking began in four countries.", "Budgets rarely label adaptation spending."]);
  assert.deepEqual(matrix.rows.map((r) => r.docId), ["a", "b"]);
  assert.deepEqual(matrix.cells, [[true, true], [true, false]]);
});

test("one report or one point gives no matrix", () => {
  assert.equal(claimsMatrix(["Only point [1]."], [source(1, "a"), source(2, "b")]), null);
  assert.equal(claimsMatrix(["One [1]. Two [2]."], [source(1, "a"), source(2, "a")]), null);
});
