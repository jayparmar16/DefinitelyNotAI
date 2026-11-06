# Retrieval evaluation set

Owner: jayparmar16
Status: in-progress

## Goal

Measure what someone researching WRI's work gets from search, without hand-labelled answers:
real questions, a model judging every passage returned, and checks that need no judgement.
A search change (per-document cap, year filter, dropping the chunk context line...) is kept
only if it raises these scores.

## Done when

- [x] `evals/questions.json` holds 16 questions: vague and specific, by year or not, single-
      and multi-document, and 2 the corpus cannot answer. No expected documents are listed.
- [x] `uv run python -m evals.run <label>` searches each question as a user types it, has the
      `answerer` model rate every passage helps / related / no (ratings cached in
      `.cache/eval/judge/`), and prints per question and in total: results, distinct
      documents, passages that help, the share from the asked-for years, whether an
      unanswerable question was declined, and coverage of the useful documents found by any
      saved run.
- [x] The scores of today's search are recorded below as the baseline.

## Baseline (4 Nov, richer-metadata search, full reload)

- 11 of 14 answerable questions get a passage that helps; 45 of 58 passages returned help.
- Results come from 1.5 documents per question on average: 9 of 14 questions draw on one
  document only.
- Three answerable questions get nothing useful: `heat-cities-2024` (2 passages, none help),
  `us-clean-energy-2025` (1, none help) and `ocean-commitments-progress` (no results, though
  *Assessing 10 Years of International Commitments to Sustainable Ocean Action* is loaded).
- `ocean-energy-2025`: 2 passages, both from one report; the offshore wind paper is missed.
- Both unanswerable questions are declined (no results).

## Handoff

None yet.
