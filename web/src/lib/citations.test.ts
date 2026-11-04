import assert from "node:assert/strict";
import { test } from "node:test";

import type { Source } from "./agent.ts";
import { citationYear, markersIn, metaLine, pageLink, splitMarkers, unmatchedMarkers } from "./citations.ts";
import { answerMarkdown, formatCitation, sourcesBibtex, sourcesCsv } from "./exports.ts";

function source(overrides: Partial<Source> = {}): Source {
  return {
    marker: 1,
    chunkId: "doc#p12-1",
    docId: "doc",
    title: "Electric bus transition",
    pubType: "Report",
    year: 2019,
    dateConfidence: "high",
    office: "WRI México",
    page: 12,
    pageCount: 40,
    passage: "fleet operators piloted buses",
    quotable: true,
    url: "https://www.wri.org/research/example",
    doi: null,
    authors: ["Author A", "Author B"],
    ...overrides,
  };
}

test("splits text and markers in order, dropping the space before a marker", () => {
  assert.deepEqual(splitMarkers("Buses ran [1] and cost fell [2][3]."), [
    { kind: "text", text: "Buses ran" },
    { kind: "marker", marker: 1 },
    { kind: "text", text: " and cost fell" },
    { kind: "marker", marker: 2 },
    { kind: "marker", marker: 3 },
    { kind: "text", text: "." },
  ]);
});

test("text without markers is one segment; brackets around words are not markers", () => {
  assert.deepEqual(splitMarkers("See [Annex] for details."), [
    { kind: "text", text: "See [Annex] for details." },
  ]);
});

test("lists markers by first use without repeats", () => {
  assert.deepEqual(markersIn(["A [2]. B [1].", "C [2] [3]."]), [2, 1, 3]);
});

test("finds markers that have no source card", () => {
  const sources = [source({ marker: 1 }), source({ marker: 2 })];
  assert.deepEqual(unmatchedMarkers(["A [1]. B [3]."], sources), [3]);
  assert.deepEqual(unmatchedMarkers(["A [1][2]."], sources), []);
});

test("page link opens wri.org at the cited page; none without a URL", () => {
  assert.equal(pageLink(source()), "https://www.wri.org/research/example#page=12");
  assert.equal(pageLink(source({ url: null })), null);
});

test("years follow the date rules: n.d. when undated, c. YEAR (file date) when low", () => {
  assert.equal(citationYear({ year: 2019, dateConfidence: "high" }), "2019");
  assert.equal(citationYear({ year: 2009, dateConfidence: "low" }), "c. 2009 (file date)");
  assert.equal(citationYear({ year: null, dateConfidence: "undated" }), "n.d.");
});

test("metadata line is type · year · office · page", () => {
  assert.equal(metaLine(source()), "Report · 2019 · WRI México · p. 12");
});

test("citation includes the DOI only when there is one", () => {
  assert.equal(
    formatCitation(source()),
    "Electric bus transition. World Resources Institute. 2019. https://www.wri.org/research/example.",
  );
  assert.match(formatCitation(source({ doi: "10.46830/x" })), /https:\/\/doi\.org\/10\.46830\/x\.$/);
});

test("CSV quotes cells with commas and quotes", () => {
  const csv = sourcesCsv([source({ title: 'Buses, "fast"' })]);
  assert.equal(csv.split("\n")[1].split(",")[1], '"Buses');
  assert.match(csv, /"Buses, ""fast"""/);
});

test("BibTeX entries carry authors and drop braces from titles", () => {
  const bib = sourcesBibtex([source({ title: "Buses {draft}" })]);
  assert.match(bib, /^@techreport\{wri2019buses1,/);
  assert.match(bib, /title = \{Buses draft\}/);
  assert.match(bib, /author = \{Author A and Author B\}/);
});

test("Markdown export keeps markers and lists every source; quotes only quotable passages", () => {
  const md = answerMarkdown("Question?", {
    mode: "quick",
    language: "en",
    machineTranslated: false,
    paragraphs: ["Buses ran [1]. Labels moved [2]."],
    sources: [source(), source({ marker: 2, quotable: false, passage: "diagram labels" })],
    claimsTotal: 2,
    claimsVerified: 2,
    elapsedSeconds: 3,
    report: null,
  });
  assert.match(md, /Buses ran \[1\]\. Labels moved \[2\]\./);
  assert.match(md, /\[1\] \[Electric bus transition\]\(https:\/\/www\.wri\.org\/research\/example#page=12\)/);
  assert.match(md, /"fleet operators piloted buses"/);
  assert.doesNotMatch(md, /"diagram labels"/);
});

test("the Markdown export labels the interpretation and keeps scope and follow-ups", () => {
  const markdown = answerMarkdown("Which laws?", {
    mode: "quick",
    language: "en",
    machineTranslated: false,
    paragraphs: ["The directive applies [1]."],
    sources: [source()],
    claimsTotal: 1,
    claimsVerified: 1,
    elapsedSeconds: 9,
    report: null,
    scope: "Based on 1 of the 5 WRI publications indexed in AskWRI",
    implications: ["Focus on transposition."],
    limits: ["No ranking of other laws."],
    questions: ["What do cities do?"],
  });
  assert.match(markdown, /_Based on 1 of the 5 WRI publications indexed in AskWRI\._/);
  assert.match(markdown, /## Possible implications \(AskWRI's interpretation, not WRI findings\)\n\n- Focus on transposition\./);
  assert.match(markdown, /## What this can't tell you\n\n- No ranking of other laws\./);
  assert.ok(markdown.indexOf("Questions to explore") < markdown.indexOf("## Sources"));
});
