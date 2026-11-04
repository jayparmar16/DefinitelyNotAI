# Ingestion 4: table chunks with captions and summaries

Owner: jayparmar16
Status: in-progress
Issue: #6 (spec: #2)

## Goal

Numbers in WRI tables become findable and citable. Each table becomes its own chunk: Markdown
rows with its caption, units and notes, plus a short model-written summary for search. The
rows can be quoted; the summary cannot.

## Done when

- [ ] Each table region becomes a chunk of kind `table` with Markdown rows, its caption,
      units, footnotes and its table number.
- [ ] Large tables are split by rows with the header repeated, never mid-row, and each piece
      is within the chunk size maximum.
- [ ] The `labeler` role writes a one- or two-sentence summary that is used for search and is
      not quotable. It is stored on the chunk so the indexer can embed it.
- [ ] Caption pairing: a table's caption is the nearest caption region or `Table N` heading on
      the same page, above or below, not only the adjacent region. A caption that is a
      `section-header` does not become a section-path heading.
- [ ] The `Notes:` and `Sources:` lines under a table belong to that table's chunk, not to a
      text chunk.
- [ ] A table continued on the next page (`(cont.)`, or the same `Table N` repeated) is linked
      to the first part: same table number, both page numbers recorded.
- [ ] A layout grid that isn't a data table (no header row of labels, no numbers) has no table
      number. It may stay a text chunk.
- [ ] Table chunks pass the audit: every cell's words are on the claimed page.
- [ ] A model refusal or error fails the document loudly.
- [ ] Tests use synthetic PDFs and the fake model client.
- [ ] The PR reports a live run on about 10 table-heavy reports: tables found, captions paired
      (and how many from a non-adjacent region), split tables, continued tables, grids
      rejected, 3 example table chunks with summaries, and the audit results.

## Handoff

None yet.
