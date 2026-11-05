/**
 * The citation map's layout: one row per year (oldest at the top), a card per report, and an
 * arrow from each report down to the later reports that cite it. Built from the visuals the
 * agent returns (timeline points and citation links); pure, so it can be tested.
 */

import type { CitationFlow, FlowLink, Relation, Timeline } from "./agent.ts";

export const WIDTH = 600;
export const CARD_W = 168;
export const CARD_H = 52;
const LABEL_W = 56; // the year column on the left
const GAP_X = 14;
const ROW_GAP = 34; // room for the arrows between rows
const PER_ROW = Math.floor((WIDTH - LABEL_W) / (CARD_W + GAP_X)); // 3 cards a row

export type MapNode = {
  docId: string;
  title: string;
  year: number | null;
  citedInAnswer: boolean;
  citedBy: number;
  lines: string[]; // the title in up to two short lines
  x: number;
  y: number;
};
export type MapEdge = {
  from: string; // the cited (earlier) report
  to: string; // the citing report
  relation: Relation;
  aspect: string;
  sentence: string;
  page: number | null;
  pdfKey: string | null;
};
export type CitationMap = { nodes: MapNode[]; edges: MapEdge[]; rows: { label: string; y: number }[]; height: number };

/** Up to two lines of at most `width` characters, the second ending in … if cut. */
export function titleLines(title: string, width = 24): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of title.split(/\s+/)) {
    if ((line + " " + word).trim().length <= width) line = (line + " " + word).trim();
    else {
      lines.push(line || word.slice(0, width));
      line = line ? word : "";
      if (lines.length === 2) break;
    }
  }
  if (lines.length < 2 && line) lines.push(line);
  const used = lines.join(" ").length;
  if (used < title.length && lines.length === 2) lines[1] = `${lines[1].slice(0, width - 1).trimEnd()}…`;
  return lines.slice(0, 2);
}

/** Every citation link once, as cited report → citing report. */
export function mapEdges(flow: CitationFlow | undefined): MapEdge[] {
  const edges = new Map<string, MapEdge>();
  const add = (from: string, to: string, link: FlowLink) => {
    const key = `${from}>${to}`;
    if (!edges.has(key)) {
      edges.set(key, { from, to, relation: link.relation, aspect: link.aspect, sentence: link.sentence, page: link.page, pdfKey: link.pdfKey });
    }
  };
  for (const f of Object.values(flow?.flows ?? {})) {
    for (const link of f.cites) add(link.docId, f.focus.docId, link);
    for (const link of f.citedBy) add(f.focus.docId, link.docId, link);
  }
  return [...edges.values()];
}

export function citationMap(timeline: Timeline, flow: CitationFlow | undefined): CitationMap {
  const points = [...timeline.points, ...timeline.undated];
  const byYear = new Map<string, typeof points>();
  for (const point of points) {
    const label = point.year ? String(point.year) : "Undated";
    byYear.set(label, [...(byYear.get(label) ?? []), point]);
  }
  const labels = [...byYear.keys()].sort((a, b) => (a === "Undated" ? 1 : b === "Undated" ? -1 : Number(a) - Number(b)));
  const nodes: MapNode[] = [];
  const rows: CitationMap["rows"] = [];
  let y = 8;
  for (const label of labels) {
    const group = byYear.get(label)!;
    rows.push({ label, y });
    group.forEach((point, i) => {
      const column = i % PER_ROW;
      const line = Math.floor(i / PER_ROW);
      nodes.push({
        docId: point.docId,
        title: point.title,
        year: point.year,
        citedInAnswer: point.citedInAnswer,
        citedBy: point.citedBy,
        lines: titleLines(point.title),
        x: LABEL_W + column * (CARD_W + GAP_X),
        y: y + line * (CARD_H + 12),
      });
    });
    y += Math.ceil(group.length / PER_ROW) * (CARD_H + 12) - 12 + ROW_GAP;
  }
  const known = new Set(nodes.map((n) => n.docId));
  const edges = mapEdges(flow).filter((e) => known.has(e.from) && known.has(e.to));
  return { nodes, edges, rows, height: Math.max(y - ROW_GAP + 16, CARD_H + 16) };
}
