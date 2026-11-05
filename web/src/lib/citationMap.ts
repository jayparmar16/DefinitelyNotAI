/**
 * The citation map's layout, drawn as a family tree: one generation per year (oldest at the
 * top), each report placed under the reports it builds on, and elbow connectors from a report
 * down to the later reports that cite it, routed around the cards in between. Reports without
 * a year can't sit in a timeline, so they are listed under the tree instead. Built from the
 * visuals the agent returns (timeline points and citation links); pure, so it can be tested.
 */

import type { CitationFlow, FlowLink, Relation, Timeline } from "./agent.ts";

export const CARD_W = 200;
export const CARD_H = 64; // two lines of title and a line of details
const LABEL_W = 72; // the year column on the left
const GAP_X = 28;
const ROW_GAP = 64; // room for the connectors between generations
const TOP = 16; // room above the first row for the "cited by" badges
const MARGIN = 28; // right of the widest row, for connectors routed around it
const LANE_CLEARANCE = 12; // how far a connector keeps from a card it passes
const CORNER = 8;

export type MapNode = {
  docId: string;
  title: string;
  year: number | null;
  citedInAnswer: boolean;
  citedBy: number;
  lines: string[]; // the title in up to two short lines
  row: number;
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
export type CitationMap = {
  nodes: MapNode[]; // the dated reports, drawn in the tree
  undated: { docId: string; title: string; citedInAnswer: boolean }[]; // listed under it
  edges: MapEdge[]; // links between drawn reports
  links: MapEdge[]; // every link, including those to undated reports (for the details)
  paths: Record<string, string>; // SVG path per drawn edge, keyed "from>to"
  rows: { label: string; y: number }[];
  width: number;
  height: number;
};

/** Up to `count` lines of at most `width` characters, the last ending in … if cut. */
export function titleLines(title: string, width = 27, count = 2): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of title.split(/\s+/)) {
    if ((line + " " + word).trim().length <= width) line = (line + " " + word).trim();
    else {
      lines.push(line || word.slice(0, width));
      line = line ? word : "";
      if (lines.length === count) break;
    }
  }
  if (lines.length < count && line) lines.push(line);
  const used = lines.join(" ").length;
  if (used < title.length && lines.length === count) {
    // Room for the "…": end on a whole word where there is one.
    const last = lines[count - 1];
    const cut = last.length < width ? last : last.slice(0, last.lastIndexOf(" ")) || last.slice(0, width - 1);
    lines[count - 1] = `${cut.trimEnd()}…`;
  }
  return lines.slice(0, count);
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

type Point = [number, number];

/** A polyline as an SVG path with rounded corners. */
export function roundedPath(points: Point[], radius = CORNER): string {
  const clean = points.filter((p, i) => i === 0 || p[0] !== points[i - 1][0] || p[1] !== points[i - 1][1]);
  let d = `M${clean[0][0]},${clean[0][1]}`;
  for (let i = 1; i < clean.length - 1; i++) {
    const [px, py] = clean[i - 1], [x, y] = clean[i], [nx, ny] = clean[i + 1];
    const into = Math.min(radius, Math.hypot(x - px, y - py) / 2);
    const out = Math.min(radius, Math.hypot(nx - x, ny - y) / 2);
    const ax = x - Math.sign(x - px) * into, ay = y - Math.sign(y - py) * into;
    const bx = x + Math.sign(nx - x) * out, by = y + Math.sign(ny - y) * out;
    d += ` L${ax},${ay} Q${x},${y} ${bx},${by}`;
  }
  const [lx, ly] = clean[clean.length - 1];
  return `${d} L${lx},${ly}`;
}

/**
 * Place each generation's reports: under the average position of the reports they link to in
 * earlier generations, then pushed apart so no two overlap. Reports linked to nothing above
 * follow on the right.
 */
function placeRow(
  group: { docId: string }[], neighbours: Map<string, string[]>, centre: Map<string, number>,
): Map<string, number> {
  const wanted = group.map((point, i) => {
    const placed = (neighbours.get(point.docId) ?? []).filter((id) => centre.has(id)).map((id) => centre.get(id)!);
    return { id: point.docId, i, at: placed.length ? placed.reduce((a, b) => a + b, 0) / placed.length - CARD_W / 2 : Infinity };
  }).sort((a, b) => a.at - b.at || a.i - b.i);
  const xs = new Map<string, number>();
  let right = -Infinity;
  for (const { id, at } of wanted) {
    const x = Math.max(Number.isFinite(at) ? at : right + GAP_X, right + GAP_X, LABEL_W);
    xs.set(id, x);
    right = x + CARD_W;
  }
  return xs;
}

/** Where connectors leave or enter a card: spread along its edge in the order of the cards at
 * their other ends, so connectors sharing a card don't pile onto one point. */
function anchors(nodes: Map<string, MapNode>, edges: MapEdge[]) {
  const centre = (id: string) => nodes.get(id)!.x + CARD_W / 2;
  const ends = new Map<string, string[]>();
  for (const e of edges) {
    ends.set(`out:${e.from}`, [...(ends.get(`out:${e.from}`) ?? []), e.to]);
    ends.set(`in:${e.to}`, [...(ends.get(`in:${e.to}`) ?? []), e.from]);
  }
  return (side: "out" | "in", id: string, other: string) => {
    const list = [...ends.get(`${side}:${id}`)!].sort((a, b) => centre(a) - centre(b));
    const share = (list.indexOf(other) + 1) / (list.length + 1);
    return nodes.get(id)!.x + CARD_W * (0.15 + 0.7 * share);
  };
}

/** An x where a connector can run down past the generations between two rows: the nearest
 * one, from `near`, that keeps clear of every card in those rows. */
function lane(nodes: MapNode[], fromRow: number, toRow: number, near: number, limit: number): number {
  const between = nodes.filter((n) => n.row > fromRow && n.row < toRow);
  const free = (x: number) => between.every((n) => x < n.x - LANE_CLEARANCE || x > n.x + CARD_W + LANE_CLEARANCE);
  for (let step = 0; step <= limit; step += 6) {
    if (free(near + step)) return near + step;
    if (near - step > LABEL_W && free(near - step)) return near - step;
  }
  return limit + MARGIN / 2;
}

function edgePaths(nodes: MapNode[], edges: MapEdge[], width: number): Record<string, string> {
  const at = new Map(nodes.map((n) => [n.docId, n]));
  const anchor = anchors(at, edges);
  // Connectors leaving the same generation turn at staggered heights, so their horizontal
  // runs don't lie on top of each other.
  const sources = [...new Set(edges.map((e) => e.from))].sort((a, b) => at.get(a)!.x - at.get(b)!.x);
  const turn = (id: string) => {
    const row = sources.filter((s) => at.get(s)!.row === at.get(id)!.row);
    return 0.3 + (0.4 * (row.indexOf(id) + 1)) / (row.length + 1);
  };
  const paths: Record<string, string> = {};
  for (const e of edges) {
    const a = at.get(e.from)!, b = at.get(e.to)!;
    const x1 = anchor("out", e.from, e.to), x2 = anchor("in", e.to, e.from);
    let points: Point[];
    if (a.row === b.row) {
      // Same year: under the row, from one card to the other.
      const y = a.y + CARD_H, below = y + ROW_GAP * turn(e.from);
      points = [[x1, y], [x1, below], [x2, below], [x2, y + 2]];
    } else {
      // Down from the earlier report to the later one (or up, if a citing report is dated
      // earlier than what it cites); past any generation in between through a free lane.
      const down = a.row < b.row;
      const upper = down ? a : b, lower = down ? b : a;
      const ux = down ? x1 : x2, lx = down ? x2 : x1;
      const y1 = upper.y + CARD_H, y2 = lower.y - (down ? 2 : 0);
      const first = y1 + ROW_GAP * turn(upper.docId);
      if (lower.row === upper.row + 1) {
        points = [[ux, y1], [ux, first], [lx, first], [lx, y2]];
      } else {
        const x = lane(nodes, upper.row, lower.row, (ux + lx) / 2, width);
        const last = lower.y - ROW_GAP * 0.35;
        points = [[ux, y1], [ux, first], [x, first], [x, last], [lx, last], [lx, y2]];
      }
      if (!down) {
        points = points.reverse();
        points[points.length - 1] = [points[points.length - 1][0], upper.y + CARD_H + 2];
      }
    }
    paths[`${e.from}>${e.to}`] = roundedPath(points);
  }
  return paths;
}

export function citationMap(timeline: Timeline, flow: CitationFlow | undefined): CitationMap {
  const dated = timeline.points.filter((p) => p.year);
  const undated = [...timeline.points.filter((p) => !p.year), ...timeline.undated];
  const years = [...new Set(dated.map((p) => p.year!))].sort((a, b) => a - b);
  const all = new Set([...dated, ...undated].map((p) => p.docId));
  const links = mapEdges(flow).filter((e) => all.has(e.from) && all.has(e.to));
  const drawn = new Set(dated.map((p) => p.docId));
  const edges = links.filter((e) => drawn.has(e.from) && drawn.has(e.to));
  const neighbours = new Map<string, string[]>();
  for (const e of edges) {
    neighbours.set(e.from, [...(neighbours.get(e.from) ?? []), e.to]);
    neighbours.set(e.to, [...(neighbours.get(e.to) ?? []), e.from]);
  }

  const nodes: MapNode[] = [];
  const rows: CitationMap["rows"] = [];
  const centre = new Map<string, number>();
  years.forEach((year, row) => {
    const y = TOP + row * (CARD_H + ROW_GAP);
    rows.push({ label: String(year), y });
    const group = dated.filter((p) => p.year === year);
    const xs = placeRow(group, neighbours, centre);
    for (const point of group) {
      const x = xs.get(point.docId)!;
      centre.set(point.docId, x + CARD_W / 2);
      nodes.push({
        docId: point.docId,
        title: point.title,
        year: point.year,
        citedInAnswer: point.citedInAnswer,
        citedBy: point.citedBy,
        lines: titleLines(point.title),
        row,
        x,
        y,
      });
    }
  });
  const right = Math.max(LABEL_W + CARD_W, ...nodes.map((n) => n.x + CARD_W));
  const width = right + MARGIN;
  return {
    nodes,
    undated: undated.map((p) => ({ docId: p.docId, title: p.title, citedInAnswer: p.citedInAnswer })),
    edges,
    links,
    paths: edgePaths(nodes, edges, right),
    rows,
    width,
    height: Math.max(TOP + years.length * (CARD_H + ROW_GAP) - ROW_GAP + 16, CARD_H + TOP + 16),
  };
}
