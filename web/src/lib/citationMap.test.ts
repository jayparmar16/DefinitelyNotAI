import assert from "node:assert/strict";
import { test } from "node:test";

import type { CitationFlow, Flow, FlowLink, Timeline } from "./agent.ts";
import { CARD_H, CARD_W, citationMap, mapEdges, roundedPath, titleLines, beyondPoints, linksCsv } from "./citationMap.ts";

const point = (docId: string, year: number | null, citedInAnswer = true) => ({ docId, title: docId, year, pubType: null, citedInAnswer, citedBy: 0 });
const link = (docId: string): FlowLink => ({ docId, title: docId, year: null, relation: "extends", aspect: "", sentence: "s", page: 3, pdfKey: null, confidence: 0.5 });
const cites = (docId: string, year: number | null, cited: string[]): Flow => ({
  focus: { docId, title: docId, year, markers: [] }, cites: cited.map(link), moreCites: 0, citedBy: [], moreCitedBy: 0, mainPoint: null,
});
const flowOf = (flows: Record<string, Flow>): CitationFlow => ({ focusOptions: [], defaultFocus: "", caption: "", flows });

/** The corners an SVG path passes through (its M and L points). */
const corners = (d: string) => [...d.matchAll(/[ML]([\d.-]+),([\d.-]+)/g)].map((m) => [Number(m[1]), Number(m[2])]);

test("each citation becomes one edge from the cited report to the citing one", () => {
  const flow = flowOf({ new: cites("new", 2016, ["old"]) });
  assert.deepEqual(mapEdges(flow).map((e) => `${e.from}>${e.to}`), ["old>new"]);
});

test("generations run from the oldest year down; undated reports are listed, not drawn", () => {
  const timeline: Timeline = { points: [point("new", 2016), point("old", 2014)], undated: [point("x", null, false)], newest: "new", caption: "" };
  const map = citationMap(timeline, flowOf({ new: cites("new", 2016, ["old"]), x: cites("x", null, ["old"]) }));
  assert.deepEqual(map.rows.map((r) => r.label), ["2014", "2016"]);
  assert.deepEqual(map.nodes.map((n) => n.docId).sort(), ["new", "old"]);
  assert.deepEqual(map.undated.map((n) => n.docId), ["x"]);
  assert.deepEqual(map.edges.map((e) => `${e.from}>${e.to}`), ["old>new"]);
  assert.equal(map.links.length, 2); // the undated report's link still shows in the details
});

test("a report sits under the report it builds on", () => {
  const timeline: Timeline = { points: [point("a", 2014), point("b", 2014), point("c", 2014), point("x", 2016)], undated: [], newest: "x", caption: "" };
  const map = citationMap(timeline, flowOf({ x: cites("x", 2016, ["c"]) }));
  const node = (id: string) => map.nodes.find((n) => n.docId === id)!;
  assert.equal(node("x").x, node("c").x);
  assert.ok(node("a").y >= 16); // room above the first row for the cited-by badge
});

test("cards in a generation never overlap", () => {
  const timeline: Timeline = { points: [point("p", 2014), point("x", 2016), point("y", 2016), point("z", 2016)], undated: [], newest: "x", caption: "" };
  const map = citationMap(timeline, flowOf({ x: cites("x", 2016, ["p"]), y: cites("y", 2016, ["p"]), z: cites("z", 2016, ["p"]) }));
  const xs = map.nodes.filter((n) => n.year === 2016).map((n) => n.x).sort((a, b) => a - b);
  for (let i = 1; i < xs.length; i++) assert.ok(xs[i] - xs[i - 1] >= CARD_W);
});

test("connectors are elbows that leave the bottom of a card and enter the top of the next", () => {
  const timeline: Timeline = { points: [point("old", 2014), point("new", 2016)], undated: [], newest: "new", caption: "" };
  const map = citationMap(timeline, flowOf({ new: cites("new", 2016, ["old"]) }));
  const old = map.nodes.find((n) => n.docId === "old")!, nu = map.nodes.find((n) => n.docId === "new")!;
  const points = corners(map.paths["old>new"]);
  assert.equal(points[0][1], old.y + CARD_H);
  assert.ok(Math.abs(points.at(-1)![1] - nu.y) <= 2);
});

test("a link that skips a generation runs through a lane clear of the cards between", () => {
  const timeline: Timeline = { points: [point("old", 2014), point("mid", 2015), point("new", 2026)], undated: [], newest: "new", caption: "" };
  const map = citationMap(timeline, flowOf({ new: cites("new", 2026, ["old"]), mid: cites("mid", 2015, ["old"]) }));
  const mid = map.nodes.find((n) => n.docId === "mid")!;
  const inMidRow = corners(map.paths["old>new"]).filter(([, y]) => y > mid.y && y < mid.y + CARD_H);
  assert.equal(inMidRow.length, 0); // no corner inside the middle row: it passes straight down
  const lane = corners(map.paths["old>new"]).find(([, y]) => y > mid.y + CARD_H)![0];
  assert.ok(lane < mid.x || lane > mid.x + CARD_W);
});

test("connectors sharing a card leave it at different points", () => {
  const timeline: Timeline = { points: [point("old", 2014), point("n1", 2016), point("n2", 2016)], undated: [], newest: "n1", caption: "" };
  const map = citationMap(timeline, flowOf({ n1: cites("n1", 2016, ["old"]), n2: cites("n2", 2016, ["old"]) }));
  assert.notDeepEqual(corners(map.paths["old>n1"])[0], corners(map.paths["old>n2"])[0]);
});

test("rounded paths keep their end points", () => {
  const d = roundedPath([[0, 0], [0, 20], [40, 20], [40, 50]]);
  assert.ok(d.startsWith("M0,0") && d.endsWith("L40,50"));
  assert.equal((d.match(/Q/g) ?? []).length, 2);
});

test("long titles fold into two short lines", () => {
  assert.deepEqual(
    titleLines("The Economic Case for Landscape Restoration in Latin America"),
    ["The Economic Case for", "Landscape Restoration in…"],
  );
  assert.deepEqual(titleLines("Short title"), ["Short title"]);
});

test("reports beyond the answer join the map only when asked, most linked first", () => {
  const timeline = { points: [point("a", 2020), point("b", 2022)], undated: [], newest: "b", caption: "" };
  const flow = flowOf({
    a: { ...cites("a", 2020, []), citedBy: [{ ...link("x"), year: 2024 }, { ...link("y"), year: 2025 }] },
    b: { ...cites("b", 2022, []), citedBy: [{ ...link("x"), year: 2024 }] },
  });
  assert.deepEqual(citationMap(timeline, flow).nodes.map((n) => n.docId).sort(), ["a", "b"]);
  const wide = citationMap(timeline, flow, { beyond: true });
  assert.deepEqual(beyondPoints(timeline, flow).map((p) => p.docId), ["x", "y"]);
  assert.ok(wide.nodes.find((n) => n.docId === "x")!.outside);
  assert.equal(wide.edges.length, 3);
});

test("only linked reports leaves out reports with no link", () => {
  const timeline = { points: [point("a", 2020), point("b", 2022), point("c", 2023)], undated: [point("u", null)], newest: "c", caption: "" };
  const flow = flowOf({ b: cites("b", 2022, ["a"]) });
  assert.deepEqual(citationMap(timeline, flow, { linkedOnly: true }).nodes.map((n) => n.docId).sort(), ["a", "b"]);
  assert.equal(citationMap(timeline, flow, { linkedOnly: true }).undated.length, 0);
});

test("an older report updated by a newer one is flagged, and links export as CSV", () => {
  const timeline = { points: [point("old", 2018), point("new", 2025)], undated: [], newest: "new", caption: "" };
  const flow = flowOf({ new: { ...cites("new", 2025, []), cites: [{ ...link("old"), relation: "updates" as const, sentence: 'Revises "2018" figures, page 4' }] } });
  const map = citationMap(timeline, flow);
  assert.deepEqual(map.nodes.find((n) => n.docId === "old")!.updatedBy, ["new"]);
  const csv = linksCsv(map).split("\n");
  assert.equal(csv[0], "citing report,citing year,relation,cited report,cited year,what it uses,page,sentence");
  assert.equal(csv[1], 'new,2025,updates,old,2018,,3,"Revises ""2018"" figures, page 4"');
});

test("a report filed twice is one card, and links between its copies are dropped", () => {
  const twin = (docId: string) => ({ ...point(docId, 2025), title: "Strengthening the Investment Case" });
  const timeline = { points: [twin("s1"), twin("s2"), point("r", 2026)], undated: [], newest: "r", caption: "" };
  const flow = flowOf({ r: cites("r", 2026, ["s1", "s2"]), s2: cites("s2", 2025, ["s1"]) });
  const map = citationMap(timeline, flow);
  assert.deepEqual(map.nodes.map((n) => n.docId).sort(), ["r", "s1"]);
  assert.deepEqual(map.edges.map((e) => `${e.from}>${e.to}`), ["s1>r"]);
});

test("reference-list mentions are hidden unless asked for", () => {
  const timeline = { points: [point("a", 2020), point("b", 2022)], undated: [], newest: "b", caption: "" };
  const flow = flowOf({ b: { ...cites("b", 2022, []), cites: [{ ...link("a"), relation: "background" }] } });
  assert.equal(citationMap(timeline, flow).edges.length, 0);
  assert.equal(citationMap(timeline, flow, { mentions: true }).edges.length, 1);
});
