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
- [x] A publication phrase ("published in 2025") becomes the year filter and leaves the
      keyword text; scored as `years`.
- [x] Keyword search matching any word of the question instead of all; scored as
      `years-anyword`.
- [x] The reranker reads each candidate's title and section before its text; scored as
      `titled-rerank`.
- [x] The question without its publication phrase is embedded and reranked too; scored as
      `titled-clean-query`.
- [x] `evals/rerankers.py` judges all 25 candidates per question and compares orderings
      (fused, Amazon Rerank, Cohere Rerank 3.5) and the cutoff; MIN_RELEVANCE set from it and
      scored as `cutoff-0.02`.
- [ ] Documents first: candidates come from the documents whose cards match best; scored as
      `documents-first`.
- [ ] Bigger chunks (1,000 to 4,000 characters) in database `askwri_big`; scored as
      `big-chunks` against the same search.
- [x] Each step's scores are recorded below, and only steps that raised them are kept.

## Scores (4 Nov, 14 answerable questions, 2 unanswerable)

| Run | Answered (a passage helps) | Passages that help | Documents per answer | Coverage |
|---|---|---|---|---|
| `baseline` | 11 | 45 of 58 | 1.5 | 1.00 (1 run) |
| `cap` (3 per document) | 13 | 33 of 51 | 2.1 | 0.94 |
| `cap6` (6 per document) | 13 | 46 of 63 | 2.1 | 0.97 |
| `cap6-more` (+ up to 10 results) | 12 | 53 of 76 | 2.3 | 0.90 |
| `cap6-more-neighbours` (+ neighbours of every hit) | 13 | 56 of 76 | 2.3 | 0.97 |
| `years` (+ publication-year filter) | 13 | 56 of 76 | 2.3 | 0.97 |
| `years-anyword` (+ keywords match any word) | 13 | 52 of 74 | 2.3 | 0.97 |
| `titled-rerank` (years, all words, + title in rerank) | 13 | 73 of 95 | 2.0 | 0.87 |
| `titled-clean-query` (+ phrase out of embedding and rerank) | 12 | 67 of 89 | 2.0 | 0.80 |
| `cutoff-0.02` (titled rerank, MIN_RELEVANCE 0.05 to 0.02) | 14 | 77 of 101 | 2.4 | 0.94 |

### Is the reranker the problem? (`python -m evals.rerankers`)

Of the 25 candidates per question, 115 help. In the top 10: fused order with no reranker 79,
Amazon Rerank 80, Cohere Rerank 3.5 85; Amazon after MIN_RELEVANCE 0.05 only 68. So the
reranker's order adds little, and the cutoff lost the most. Off-topic passages scored at most
0.003 on Amazon and the unanswerable questions' best candidates at most 0.006, so 0.02 keeps
80 of the passages that help and still declines both. Cohere orders better but cannot decline:
it scored the Germany near miss 0.62, above a quarter of the passages that help. Two
questions are not reranker problems: `us-clean-energy-2025` has no candidate that helps, and
`heat-cities-2024` has 12 that help but no ordering puts more than 3 in the top 10.

Both unanswerable questions were declined in every run. Kept: a cap of 6, up to 10 results,
neighbours on every hit and the publication-year filter. The year filter changed no score:
both "published in" questions already got only documents from their year, so it is kept for
correctness, not for these scores. Any-word keywords were dropped: without a weight for rare
words, common ones pushed good passages out (climate finance fell from 3 helping passages to
1, school-bus barriers from 7 to 5). A cap of 3 starved questions answered by one document (offshore
wind India fell from 5 helping passages to 1). One question's results differ by a passage
between identical runs (the vector index scan is approximate), so a change of one passage on
one question is noise; read the totals.

Kept also: the title and section in the reranker's text (73 helping passages from 56;
`heat-cities-2024` answered for the first time; `ocean-energy-2025` from 2 to 5). It ends
`ai-for-nature`'s three answers, which were RFP passages scoring just over MIN_RELEVANCE;
with "Request for Proposals" in view the reranker scores them about 0.02. Dropped: removing
the publication phrase from the embedding and rerank, which left `ocean-energy-2025` with no
result above MIN_RELEVANCE.

Still failing:
- `ai-for-nature`: *AI for Nature* (working paper) is a candidate only through its cover
  page; none of its body passages are retrieved.
- `ocean-energy-2025`: all 5 passages come from one report; the offshore wind paper is not
  among the candidates (6 documents), though its card is the 5th closest of 217 2025 cards.
  Documents-first search through the cards is the next thing to score.

## Handoff

None yet.
