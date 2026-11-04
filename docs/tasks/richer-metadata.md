# Richer document metadata for vague questions

Owner: jayparmar16
Status: in-progress

## Goal

Vague questions ("trends for ocean renewable energies published in 2025") find too little:
61% of documents have no year, wri.org labels we fetch are thrown away, and a document's
topics, concepts and places are not in what search embeds. This task adds rule-based labels
(A) and one `labeler` call per document (B) to the ingestion into Aurora.

## Done when

- [ ] Every document's `year` comes from its publication date, else from its corpus folder
      (`2024`, `2025`, `2026`); `date_source` says which (`wri.org`, `model` or `folder`).
- [ ] wri.org documents store the page's description as `abstract`, and the initiatives and
      programs named in its "This ... is part of ... within ..." line.
- [ ] WRI's tags are sorted into `topics` (the 11) and `concepts` (one controlled
      vocabulary, matched ignoring case); `tags` keeps WRI's originals.
- [ ] Each document stores the acronyms its text defines, e.g. `OSW = Offshore wind`.
- [ ] Chunks under References, Notes, Contents, Acknowledgements, About and Abbreviations
      headings get a `role`, and search skips them.
- [ ] One `labeler` call per document adds topics, concepts, keywords, countries, regions,
      key findings, genre and coverage years, added after WRI's own labels, never replacing them.
- [ ] Each chunk's embedded text carries the document's year, topics, concepts, initiative
      and places.
- [ ] Each document has a card: a keyword index (`doc_tsv`) and an embedding
      (`card_embedding`) of its title, abstract or summary, labels and key findings.
- [ ] `db/schema.sql` upgrades the existing database in place, and `--reload` reloads
      PDFs whose files have not changed.
- [ ] No new tests for the labels (decided with the user), beyond the wri.org taxonomy line;
      `docs/richer-metadata.md` says how to check each item by hand.

## Handoff

None yet.
