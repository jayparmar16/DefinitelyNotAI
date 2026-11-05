/** Fact-check helpers: where each claim sits in the draft, and the report as Markdown. */

import type { CheckedClaim, FactCheck, Verdict } from "./agent.ts";

export const VERDICT_NAMES: Record<Verdict, string> = {
  supported: "Supported",
  contradicted: "Contradicted",
  outdated: "Outdated",
  not_found: "Not found",
};

/** One stretch of the draft: plain text, or the words of claim `claim` (an index). */
export type Segment = { text: string; claim: number | null };

/**
 * Split the draft into plain stretches and claim quotes, so each claim can be coloured where it
 * was written. Quotes are found in order (exact first, then ignoring case); a quote the model
 * didn't copy exactly, or one overlapping an earlier claim, is simply left unhighlighted.
 */
export function annotate(draft: string, claims: CheckedClaim[]): Segment[] {
  const found: { start: number; end: number; claim: number }[] = [];
  const lower = draft.toLowerCase();
  claims.forEach((claim, index) => {
    const quote = claim.quote.trim();
    if (!quote) return;
    let start = draft.indexOf(quote);
    if (start < 0) start = lower.indexOf(quote.toLowerCase());
    if (start < 0) return;
    const end = start + quote.length;
    if (found.some((f) => start < f.end && end > f.start)) return;
    found.push({ start, end, claim: index });
  });
  found.sort((a, b) => a.start - b.start);
  const segments: Segment[] = [];
  let at = 0;
  for (const f of found) {
    if (f.start > at) segments.push({ text: draft.slice(at, f.start), claim: null });
    segments.push({ text: draft.slice(f.start, f.end), claim: f.claim });
    at = f.end;
  }
  if (at < draft.length) segments.push({ text: draft.slice(at), claim: null });
  return segments;
}

/** "3 supported · 1 contradicted · 1 not found" (verdicts with no claims left out). */
export function countsLine(check: FactCheck): string {
  const parts = (Object.keys(VERDICT_NAMES) as Verdict[])
    .filter((verdict) => check.counts[verdict])
    .map((verdict) => `${check.counts[verdict]} ${VERDICT_NAMES[verdict].toLowerCase()}`);
  return `${check.claims.length} claim${check.claims.length === 1 ? "" : "s"}: ${parts.join(" · ")}`;
}

/** The fact-check as Markdown: each claim with its verdict, correction and sources. */
export function factCheckMarkdown(check: FactCheck): string {
  const lines = ["# Fact-check against WRI publications", "", `_${countsLine(check)}._`, ""];
  for (const claim of check.claims) {
    const markers = claim.markers.map((m) => `[${m}]`).join("");
    lines.push(`- **${VERDICT_NAMES[claim.verdict]}**: ${claim.quote} ${markers}`.trimEnd());
    if (claim.correction) lines.push(`  - Suggested wording: ${claim.correction}`);
    if (claim.note) lines.push(`  - ${claim.note}`);
  }
  lines.push("", "## Sources", "");
  for (const source of check.sources) {
    lines.push(`[${source.marker}] ${source.title}. ${source.pubType}, ${source.year ?? "n.d."}, p. ${source.printedPage ?? source.page}.`);
  }
  return `${lines.join("\n")}\n`;
}

/** A note that opens with a source number reads "Source [1] gives…", not a bare "1 gives…". */
export function noteText(note: string): string {
  return /^\[\d+\]/.test(note.trim()) ? `Source ${note.trim()}` : note;
}
