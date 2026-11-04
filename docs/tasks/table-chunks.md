# Ingestion 4: table chunks with captions and summaries

Owner: jayparmar16
Status: in-review
Issue: #6 (spec: #2)

## Goal

Numbers in WRI tables become findable and citable. Each table becomes its own chunk: Markdown
rows with its caption, units and notes, plus a short model-written summary for search. The
rows can be quoted; the summary cannot.

## Done when

- [x] Each table region becomes a chunk of kind `table` with Markdown rows, its caption,
      units, footnotes and its table number.
- [x] Large tables are split by rows with the header repeated, never mid-row, and each piece
      is within the chunk size maximum.
- [x] The `labeler` role writes a one- or two-sentence summary that is used for search and is
      not quotable. It is stored in the chunk's `description` so the indexer can embed it.
- [x] Caption pairing: a table's caption is the nearest caption region or `Table N` heading on
      the same page, above or below, not only the adjacent region. A caption that is a
      `section-header` does not become a section-path heading.
- [x] The `Notes:` and `Sources:` lines under a table belong to that table's chunk, not to a
      text chunk.
- [x] A table continued on the next page (`(cont.)`, or the same `Table N` repeated) is linked
      to the first part: same table number, both page numbers recorded.
- [x] A layout grid that isn't a data table (no header row of labels, no numbers) has no table
      number. It may stay a text chunk.
- [x] Table chunks pass the audit: every cell's words are on the claimed page.
- [x] A model refusal or error fails the document loudly.
- [x] Tests use synthetic PDFs and the fake model client.
- [x] The PR reports a live run on about 10 table-heavy reports: tables found, captions paired
      (and how many from a non-adjacent region), split tables, continued tables, grids
      rejected, 3 example table chunks with summaries, and the audit results.

## Notes

- Chunk fields: `number` ("Table 2"), `table_first_chunk` (chunk_id of the first piece of a
  table cut by rows or continued on a later page) and `description` (the model summary; part
  of `indexed_text`, never in `text`).
- Table rows are quotable per row: the audit checks each row on its own, since text layers
  often read a table column by column.
- The live Haiku run was blocked: the sandbox session token in `.env` had expired (HTTP 403).
  The evidence in the PR is from a run without model calls; descriptions are covered by tests
  with the fake client. Rerun `ingest_document` with a client on the 10 reports once
  credentials are refreshed.

## Handoff

None yet.
