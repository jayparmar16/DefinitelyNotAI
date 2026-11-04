# Ingestion 2b: chunk sizes and order for Aurora pgvector

Owner: jayparmar16
Status: in-review
Issue: #20 (spec: #2)

## Goal

Size chunks for search over Aurora pgvector with Titan Text Embeddings V2: no tiny chunks
that crowd real passages out of the top results, no chunk over the size cap, and a `seq` on
every chunk so retrieval can fetch a short hit's neighbours with one SQL query.

## Done when

- [x] Chunks aim for about 100-500 tokens (roughly 400-2,000 characters). The two limits are
      plain constants in the chunker, with a comment that they're a starting point to tune.
- [x] A block shorter than the minimum merges with the next block in the same section, or
      with the previous chunk at the end of a section. A section whose whole text is under
      the minimum stays one short chunk. Chunks never cross a heading.
- [x] A single block longer than the maximum is split at sentence boundaries. No chunk
      exceeds the maximum unless one sentence does.
- [x] Every chunk gets `seq`, its position in the document's chunk order: contiguous from 1
      and identical across reruns. `chunk_id` keeps its format.
- [x] Page ranges and printed pages (#4) stay correct, and the audit still passes on both
      40-PDF samples with 0 documents failing.
- [x] The PR reports the chunk size distribution before and after on the same sample: count,
      median, share under 400 characters, and maximum.
- [x] Docstrings and README no longer describe chunk text as Bedrock Knowledge Bases input.
- [x] Tests use synthetic PDFs: short lines and paragraphs merge within a section, never
      across a heading; an over-long paragraph splits at sentences; `seq` is contiguous and
      stable.

## Notes

- On the 20-report sample, 215 of the 222 chunks still under 400 characters are the whole
  text of a section (a heading followed by a line such as "University of Ghana" or "Source:
  Authors."). The rule that chunks never cross a heading keeps them short. Merging them
  across headings would need a different rule.
- A short last chunk is fixed by re-dividing the last two chunks at a block boundary. If no
  block boundary puts both in the band, it stays short (7 chunks on the sample).

## Handoff

None yet.
