# Ingestion 2: printed page numbers, page ranges and running headers/footers

Owner: jayparmar16
Status: in-review
Issue: #4 (spec: #2)

## Goal

Citations show the page number readers see, not just the position in the file. Chunks that
cross a page break record their page range, and running headers and footers never leak into
chunk text.

## Done when

- [x] `printed_page` comes from the PDF's page labels where defined, else from the page-header
      or page-footer region, else falls back to `pdf_page` and is flagged.
- [x] A document with Roman-numeral front matter gives `printed_page` values that differ
      correctly from `pdf_page`.
- [x] A chunk spanning a page break records both page ranges (PDF and printed), and the audit
      checks it against both pages.
- [x] Text from page-header and page-footer regions appears in no chunk (checked on synthetic
      and on real PDFs).
- [x] Covered by tests on synthetic PDFs with page labels and running headers/footers.
- [x] Chunk IDs stay stable and based on the start page; the 40-PDF regression samples still
      show 0 documents failing.

## Notes

- Printed numbers read from header/footer text count only when two or more pages agree on
  the same offset from the PDF page; a lone number (a year, "Step 1") is ignored.
- The layout model sometimes classes one page's running header as body text, so text equal
  to a header or footer seen elsewhere in the document is dropped (found on real PDFs).
- Chunks now run across page breaks: about 12% fewer chunks on both 40-PDF samples.
- `volumetric-water-benefit-accounting-2-0.pdf` fails the audit on main too ("picture"
  placeholder text from the layout Markdown); not in scope here.

## Handoff

None yet.
