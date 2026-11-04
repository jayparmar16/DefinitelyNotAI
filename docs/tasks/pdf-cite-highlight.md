# Highlight the cited passage in the PDF side panel

**Goal.** Clicking a source opens the stored PDF at the cited page with the cited text
highlighted and scrolled into view.

**Done when**
- [x] The side panel draws the cited page with PDF.js (canvas + text layer) instead of the
      browser's PDF viewer, which our page can't reach into.
- [x] The passage is found in the page's text layer, comparing letters and digits only
      (NFKC, lower case), so whitespace, case, hyphenated line breaks, ligatures and quote
      styles don't matter. Matches are wrapped in `<mark class="cite-highlight">` (yellow,
      translucent) and the first is scrolled into view.
- [x] A passage that continues on the next page, or whose page text is in a different order
      (columns, text boxes), highlights what is on the cited page; nothing is highlighted
      rather than something wrong (matches under 24 characters are dropped).
- [x] Unit tests for the matching (`src/lib/highlight.test.ts`).
- [x] Checked on real data: 47 passages from the deployed search, cited pages extracted with
      PDF.js: 47 highlighted, 39 of them at 80% or more (the rest continue on the next page or
      sit in a separate text box).
- [ ] Corpus bucket CORS (GET/HEAD from `allowed_origins`) applied, then a browser check.

**Notes.** One new dependency: `pdfjs-dist` 6.4.299 (Mozilla's PDF renderer, the standard way
to draw a PDF page with a searchable text layer). The PDF is downloaded once per document and
kept for the session, since presigned links expire after 5 minutes. "Open full PDF" still opens
the browser's viewer at the page. Mock sources have no stored PDF and show the passage only.
