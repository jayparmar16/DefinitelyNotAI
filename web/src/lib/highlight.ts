/**
 * Finding a cited passage in a PDF page's text layer, so the viewer can highlight it.
 *
 * Text is compared on letters and digits only (Unicode NFKC, lower case): that ignores
 * whitespace, case, hyphenated line breaks, ligatures, quote styles and how the PDF split
 * its text into spans, which differ between the page and the stored passage.
 */

/** One stretch of a span's text to highlight: [start, end) are offsets in that span's text. */
export type SpanRange = { span: number; start: number; end: number };

const KEEP = /[\p{L}\p{N}]/u;
const MIN_MATCH = 24; // normalised characters: shorter matches could be coincidence
const WINDOW = 32; // passage pieces searched one by one when the whole passage isn't on the page

/** The comparable form of a text: letters and digits only, NFKC, lower case. */
export function normalize(text: string): string {
  let out = "";
  for (const char of text.normalize("NFKC").toLowerCase()) if (KEEP.test(char)) out += char;
  return out;
}

/** The page's spans as one comparable string, with the span and offset each character came from. */
export function pageStream(spans: string[]): { text: string; origin: { span: number; offset: number }[] } {
  let text = "";
  const origin: { span: number; offset: number }[] = [];
  spans.forEach((spanText, span) => {
    for (let offset = 0; offset < spanText.length; offset++) {
      for (const char of spanText[offset].normalize("NFKC").toLowerCase()) {
        if (!KEEP.test(char)) continue;
        text += char;
        origin.push({ span, offset });
      }
    }
  });
  return { text, origin };
}

/**
 * Where the passage appears in the page stream, as [start, end) ranges. The whole passage if
 * it is all on the page; otherwise the runs of its pieces found (a passage can carry on to the
 * next page, or columns can order the text differently). Short runs are dropped.
 */
export function findPassage(stream: string, passage: string): [number, number][] {
  const wanted = normalize(passage);
  if (wanted.length < MIN_MATCH) return [];
  const whole = stream.indexOf(wanted);
  if (whole >= 0) return [[whole, whole + wanted.length]];

  const runs: [number, number][] = [];
  let from = 0;
  for (let i = 0; i + WINDOW <= wanted.length; i += WINDOW) {
    const piece = wanted.slice(i, i + WINDOW);
    // In reading order first; then anywhere, since columns and text boxes can put a PDF's text
    // in a different order from the passage.
    let at = stream.indexOf(piece, from);
    if (at < 0) at = stream.indexOf(piece);
    if (at < 0) continue;
    const last = runs.at(-1);
    if (last && last[1] === at) last[1] = at + WINDOW;
    else runs.push([at, at + WINDOW]);
    from = at + WINDOW;
  }
  // A tail shorter than a window still belongs to a run that reaches it.
  const tail = wanted.length % WINDOW;
  const last = runs.at(-1);
  if (tail && last && stream.startsWith(wanted.slice(-tail), last[1])) last[1] += tail;
  return runs.filter(([start, end]) => end - start >= MIN_MATCH);
}

/** Turn stream ranges into one highlight range per span, in span order. */
export function spanRanges(
  ranges: [number, number][],
  origin: { span: number; offset: number }[],
): SpanRange[] {
  const bySpan = new Map<number, SpanRange>();
  for (const [start, end] of ranges) {
    for (let i = start; i < end; i++) {
      const { span, offset } = origin[i];
      const range = bySpan.get(span);
      if (!range) bySpan.set(span, { span, start: offset, end: offset + 1 });
      else {
        range.start = Math.min(range.start, offset);
        range.end = Math.max(range.end, offset + 1);
      }
    }
  }
  return [...bySpan.values()].sort((a, b) => a.span - b.span);
}

/** The highlight ranges for a passage on a page whose text layer has these span texts. */
export function highlightRanges(spans: string[], passage: string): SpanRange[] {
  const { text, origin } = pageStream(spans);
  return spanRanges(findPassage(text, passage), origin);
}
