# Retrieval evaluation set

Owner: jayparmar16
Status: in-progress

## Goal

A small set of real questions, each with the WRI documents a good answer should cite, and a
script that scores `search_passages()` against it. Search changes (dropping the chunk context
line, a per-document cap, year and topic filters) are kept only if they raise the score.

## Done when

- [ ] `eval/questions.json` holds 10 to 15 questions: vague and specific, filtered by year or
      not, single- and multi-document, plus at least one the corpus cannot answer. Each lists
      the `doc_id`s a good answer cites and any filters a user would pass.
- [ ] Every expected `doc_id` exists in Aurora, and the user has reviewed the expected documents.
- [ ] `uv run python -m eval.run` prints, per question and in total, how many expected documents
      appear in the results, how many distinct documents the results come from, and whether an
      unanswerable question returned nothing.
- [ ] The scores of today's search are recorded in this file as the baseline.

## Handoff

None yet.
