/** Citation markers in answer text: split "... routes [1][2]." into text and marker parts. */

import type { Source } from "./agent.ts";

export type Segment = { kind: "text"; text: string } | { kind: "marker"; marker: number };

const MARKER = /\s*\[(\d+)\]/g;

/** Split text into plain-text and [n] marker segments, in order. Spaces before a marker drop. */
export function splitMarkers(text: string): Segment[] {
  const segments: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(MARKER)) {
    if (match.index > last) segments.push({ kind: "text", text: text.slice(last, match.index) });
    segments.push({ kind: "marker", marker: Number(match[1]) });
    last = match.index + match[0].length;
  }
  if (last < text.length) segments.push({ kind: "text", text: text.slice(last) });
  return segments;
}

/** Markers used in the texts, in order of first use, without repeats. */
export function markersIn(texts: string[]): number[] {
  const seen = new Set<number>();
  for (const text of texts) {
    for (const segment of splitMarkers(text)) {
      if (segment.kind === "marker") seen.add(segment.marker);
    }
  }
  return [...seen];
}

/**
 * Markers in the texts that have no source card. The UI refuses to show an answer with any,
 * because a marker without a source is an uncited claim (design doc: "every marker maps to one
 * source entry").
 */
export function unmatchedMarkers(texts: string[], sources: Source[]): number[] {
  const known = new Set(sources.map((source) => source.marker));
  return markersIn(texts).filter((marker) => !known.has(marker));
}

/** Link that opens the source on wri.org at the cited page, or null without a URL. */
export function pageLink(source: Source): string | null {
  return source.url ? `${source.url}#page=${source.page}` : null;
}

/** Year as citations show it: "2019", "c. 2009 (file date)" for low confidence, else "n.d.". */
export function citationYear(source: Pick<Source, "year" | "dateConfidence">): string {
  if (source.year === null || source.dateConfidence === "undated") return "n.d.";
  return source.dateConfidence === "low" ? `c. ${source.year} (file date)` : String(source.year);
}

/** Metadata line in WRI's fixed order: type · year · office · page. */
export function metaLine(source: Source): string {
  return [source.pubType, citationYear(source), source.office, `p. ${source.page}`].join(" · ");
}
