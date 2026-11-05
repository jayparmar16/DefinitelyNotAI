/**
 * The welcome line: "Ask" followed by a short fact about WRI's research, changing every few
 * seconds. Every fact is true of the collection as loaded (Nov 2026): 580 publications from 2014
 * to 2026, 1,344 images and 945 charts described, answers in four languages. Each phrase fits
 * one line, so the page doesn't move when it changes.
 */

export const FACT_SECONDS = 5;

/** The five phrases after "Ask"; inside a space the first names that space's publications. */
export function askFacts(space: string | null, documents: number | null): string[] {
  const first = space
    ? `${documents ?? "the"} WRI publications on ${space.toLowerCase()}`
    : "580 WRI publications";
  return [
    first,
    "12 years of WRI research",
    "why grid forecasts doubled",
    "2,000+ WRI charts and maps",
    "in your own language",
  ];
}
