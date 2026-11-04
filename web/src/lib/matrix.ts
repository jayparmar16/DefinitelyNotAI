/**
 * The evidence matrix for any answer: which report backs which point. Built from the answer's own
 * [n] markers, so it needs no model call; a lens or dossier gives a fuller, per-aspect matrix.
 */

import type { Source } from "./agent.ts";

export type ClaimsMatrix = {
  columns: { label: string; text: string }[];
  rows: { docId: string; title: string; year: number | null }[];
  cells: boolean[][]; // cells[row][column]: the report is cited for that point
};

const MAX_POINTS = 6;

/** Short label for a sentence: its first words, without markers. */
function label(sentence: string): string {
  const words = sentence.replace(/\s*\[\d+\]/g, "").split(/\s+/);
  return words.length > 7 ? `${words.slice(0, 7).join(" ")}…` : words.join(" ");
}

export function claimsMatrix(paragraphs: string[], sources: Source[]): ClaimsMatrix | null {
  const docOf = new Map(sources.map((s) => [s.marker, s.docId]));
  const points = paragraphs
    .flatMap((p) => p.split(/(?<=[.!?])\s+(?=[A-Z¿¡])/))
    .map((text) => ({ text, docs: new Set([...text.matchAll(/\[(\d+)\]/g)].map((m) => docOf.get(Number(m[1]))).filter(Boolean)) }))
    .filter((point) => point.docs.size > 0)
    .slice(0, MAX_POINTS);
  const rows = [...new Map(sources.map((s) => [s.docId, { docId: s.docId, title: s.title, year: s.year }])).values()];
  if (points.length < 2 || rows.length < 2) return null; // one report or one point: nothing to compare
  return {
    columns: points.map((p) => ({ label: label(p.text), text: p.text })),
    rows,
    cells: rows.map((row) => points.map((p) => p.docs.has(row.docId))),
  };
}
