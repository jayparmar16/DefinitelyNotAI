# Search tuning against the evaluation set

Owner: jayparmar16
Status: in-progress

## Goal

Answers draw on 1.5 documents per question and miss useful ones (docs/tasks/retrieval-eval.md).
Change `search_passages()` step by step, keeping each change only if `evals.run` scores rise.

## Done when

- [ ] Fused candidates are capped per document before reranking; scored as `cap`.
- [ ] More passages go to the answering model; scored as `cap-more`.
- [ ] More surrounding text goes to the answering model (neighbours of every hit, in place of
      bigger embedded chunks); scored as `cap-more-neighbours`.
- [ ] Each step's scores are recorded below, and only steps that raised them are kept.

## Handoff

None yet.
