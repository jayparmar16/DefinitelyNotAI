/**
 * The evidence matrix for any answer: which report backs which point. Built from the answer's own
 * [n] markers, so it needs no model call; a lens or dossier gives a fuller, per-aspect matrix.
 * Columns carry short headings (the agent's 1-3 word theme per paragraph or key point) so the
 * whole matrix fits in one view; the full point shows on hover.
 */

import type { Source } from "./agent.ts";

export type MatrixRow = { key: string; title: string; meta: string };

export type ClaimsMatrix = {
  columns: { label: string; text: string }[];
  rows: MatrixRow[];
  cells: boolean[][]; // cells[row][column]: the report is cited for that point
};

const MAX_POINTS = 6;

/** "Report · 2025": the same line under every matrix's publication names. */
export function rowMeta(pubType: string | null | undefined, year: number | null | undefined): string {
  return [pubType, year ?? "n.d."].filter(Boolean).join(" · ");
}

// The same report is sometimes filed twice (two folders, two doc IDs): one row by title.
const titleKey = (title: string) => title.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

type Point = { text: string; label: string; docs: Set<string> };

function cited(text: string, docOf: Map<number, string>): Set<string> {
  return new Set([...text.matchAll(/\[(\d+)\]/g)].map((m) => docOf.get(Number(m[1]))).filter((d): d is string => Boolean(d)));
}

function points(paragraphs: string[], themes: string[], docOf: Map<number, string>): Point[] {
  const strip = (text: string) => text.replace(/\s*\[\d+\]/g, "");
  // One column per paragraph or key point, headed by its theme, when there are two or more.
  const byParagraph = paragraphs
    .map((text, i) => ({ text: strip(text), label: themes[i]?.trim() || `Point ${i + 1}`, docs: cited(text, docOf) }))
    .filter((point) => point.docs.size > 0);
  if (byParagraph.length >= 2) return byParagraph.slice(0, MAX_POINTS);
  // A single paragraph: one column per cited sentence instead, numbered.
  return paragraphs
    .flatMap((p) => p.split(/(?<=[.!?])\s+(?=[A-Z¿¡])/))
    .map((text) => ({ text: strip(text), docs: cited(text, docOf) }))
    .filter((point) => point.docs.size > 0)
    .slice(0, MAX_POINTS)
    .map((point, i) => ({ ...point, label: `Point ${i + 1}` }));
}

export function claimsMatrix(paragraphs: string[], sources: Source[], themes: string[] = []): ClaimsMatrix | null {
  const docOf = new Map(sources.map((s) => [s.marker, s.docId]));
  const columns = points(paragraphs, themes, docOf);
  const rows = new Map<string, MatrixRow & { docs: Set<string> }>();
  for (const s of sources) {
    const key = titleKey(s.title);
    const row = rows.get(key) ?? { key, title: s.title, meta: rowMeta(s.pubType, s.year), docs: new Set<string>() };
    row.docs.add(s.docId);
    rows.set(key, row);
  }
  const list = [...rows.values()];
  if (columns.length < 2 || list.length < 2) return null; // one report or one point: nothing to compare
  return {
    columns: columns.map((p) => ({ label: p.label, text: p.text })),
    rows: list.map(({ key, title, meta }) => ({ key, title, meta })),
    cells: list.map((row) => columns.map((p) => [...row.docs].some((d) => p.docs.has(d)))),
  };
}
