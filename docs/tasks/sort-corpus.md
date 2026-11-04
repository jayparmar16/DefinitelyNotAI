# Ingestion 8: sort the corpus

Owner: jayparmar16
Status: in-review
Issue: #10 (spec: #2)

## Goal

Only the right documents get ingested. Duplicates and older versions are dropped, non-English
files are dropped while the English twin is kept, and each document is typed. Every dropped
file is reported with its reason.

## Done when

- [x] Exact duplicates are found by content hash.
- [x] Version families (version markers such as 2.0 and 2.1, and `_0` suffixes) keep only the
      latest version, and the kept document records which version(s) it replaces.
- [x] Language is detected from the first pages with a stopword-ratio heuristic (standard
      library only). Non-English files are dropped, and the English twin is kept.
- [x] Document type is one of: research report, working paper, issue brief, technical note,
      newsletter, RFP, dataset documentation, annual report, other.
- [x] The result lists kept documents and dropped documents with a reason each.
- [x] Kept documents have unique `doc_id`s.
- [x] Tests use synthetic PDFs.
- [x] A command prints the sorting report for a folder list; run on the full corpus, with the
      numbers in the PR body.

## Notes

- Families match on the normalised file name only. The spec also says "title", but PDF
  metadata titles merged different documents (one ANBI form per fiscal year share a title)
  and found no real family that the file name missed.
- `_0`, `_1` are not exact copies in this corpus: they are re-uploads with small edits, so
  the higher suffix is treated as the later version. When two files in a family tie on
  version, the later year folder wins.
- A file with too little text to judge is kept with language `unknown`, because dropping
  on no evidence loses documents and the ingestion audit already reports pages without text.
  A file with text in a language we have no stopwords for (Hindi in a legacy font,
  Vietnamese) is dropped as not English.
- A duplicate or non-English file is never part of a version family, so a Spanish file can't
  cause its English twin to be dropped as an older version.
- Two kept documents with the same `doc_id` stop the sort with an error rather than being
  renamed. With the corpus as it is, none do.

## Handoff

None yet.
