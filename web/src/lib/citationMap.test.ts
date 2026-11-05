import assert from "node:assert/strict";
import { test } from "node:test";

import type { CitationFlow, Timeline } from "./agent.ts";
import { citationMap, mapEdges, titleLines } from "./citationMap.ts";

const point = (docId: string, year: number | null, citedInAnswer = true) => ({ docId, title: docId, year, pubType: null, citedInAnswer, citedBy: 0 });
const link = (docId: string) => ({ docId, title: docId, year: null, relation: "extends" as const, aspect: "", sentence: "s", page: 3, pdfKey: null, confidence: 0.5 });

const flow: CitationFlow = {
  focusOptions: [], defaultFocus: "new", caption: "",
  flows: {
    new: { focus: { docId: "new", title: "new", year: 2016, markers: [1] }, cites: [link("old")], moreCites: 0, citedBy: [], moreCitedBy: 0, mainPoint: null },
    old: { focus: { docId: "old", title: "old", year: 2014, markers: [2] }, cites: [], moreCites: 0, citedBy: [link("new")], moreCitedBy: 0, mainPoint: null },
  },
};

test("each citation becomes one edge from the cited report to the citing one", () => {
  assert.deepEqual(mapEdges(flow).map((e) => `${e.from}>${e.to}`), ["old>new"]);
});

test("rows run from the oldest year down, with undated reports last", () => {
  const timeline: Timeline = { points: [point("new", 2016), point("old", 2014)], undated: [point("x", null, false)], newest: "new", caption: "" };
  const map = citationMap(timeline, flow);
  assert.deepEqual(map.rows.map((r) => r.label), ["2014", "2016", "Undated"]);
  const y = (id: string) => map.nodes.find((n) => n.docId === id)!.y;
  assert.ok(y("old") < y("new") && y("new") < y("x"));
  assert.equal(map.edges.length, 1);
});

test("long titles fold into two short lines", () => {
  assert.deepEqual(titleLines("The Economic Case for Landscape Restoration in Latin America"), ["The Economic Case for", "Landscape Restoration i…"]);
  assert.deepEqual(titleLines("Short title"), ["Short title"]);
});
