# Hybrid search with filters and rerank

Owner: jayparmar16
Status: in-review
Issue: #19

## Goal

`search_passages()`: one function the answering agent calls to get the best 6 cited passages
for a question, from the Aurora index, for the 5 Nov demo.

## Done when

- [x] One SQL statement fuses pgvector and full-text rankings (RRF) with year, topic, type and
      country filters; the top 25 are reranked with Amazon Rerank 1.0 and the best 6 returned.
- [x] Short hits come back with their previous and next chunk of the same section.
- [x] Fewer matches than 6 are never padded; none returns an empty list.
- [x] Tests with fakes cover filters, rerank order and cut, no padding and neighbours.
- [x] `python -m askwri.search` runs live and is documented in the README.

## Handoff

None yet.
