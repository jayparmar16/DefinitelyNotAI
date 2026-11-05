# Search tuning against the evaluation set

Owner: jayparmar16
Status: in-progress

## Goal

Answers draw on 1.5 documents per question and miss useful ones (docs/tasks/retrieval-eval.md).
Change `search_passages()` step by step, keeping each change only if `evals.run` scores rise.

## Done when

- [x] Fused candidates are capped per document before reranking; scored as `cap` (3) and `cap6` (6).
- [x] More passages go to the answering model; scored as `cap-more`.
- [x] More surrounding text goes to the answering model (neighbours of every hit, in place of
      bigger embedded chunks); scored as `cap-more-neighbours`.
- [x] Each step's scores are recorded below, and only steps that raised them are kept.

## Scores (4 Nov, 14 answerable questions, 2 unanswerable)

| Run | Answered (a passage helps) | Passages that help | Documents per answer | Coverage |
|---|---|---|---|---|
| `baseline` | 11 | 45 of 58 | 1.5 | 1.00 (1 run) |
| `cap` (3 per document) | 13 | 33 of 51 | 2.1 | 0.94 |
| `cap6` (6 per document) | 13 | 46 of 63 | 2.1 | 0.97 |
| `cap6-more` (+ up to 10 results) | 12 | 53 of 76 | 2.3 | 0.90 |
| `cap6-more-neighbours` (+ neighbours of every hit) | 13 | 56 of 76 | 2.3 | 0.97 |

Both unanswerable questions were declined in every run. Kept: a cap of 6, up to 10 results
and neighbours on every hit. A cap of 3 starved questions answered by one document (offshore
wind India fell from 5 helping passages to 1). One question's results differ by a passage
between identical runs (the vector index scan is approximate), so a change of one passage on
one question is noise; read the totals.

Still failing: `heat-cities-2024` (nothing helps) and `ocean-energy-2025` (2 passages from one
report; the offshore wind paper is never a candidate).

## Handoff

None yet.
