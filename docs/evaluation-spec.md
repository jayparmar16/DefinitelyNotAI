# AskWRI evaluation: what to run

A brief for whoever runs the evaluation. It says what to measure, how, against which targets,
and what to hand back. The code to run most of it already exists; parts 3 to 5 need new test
items, written in the same format as `eval/testset.jsonl`.

## Ground rules

- Branch `askwri-cognito`. Team AWS account only, profile `hackathon`, region `us-west-2`.
- Never run `terraform apply`, `terraform destroy` or `scripts/run-pipeline.sh`, and don't change
  agent, tool or infra code. Report problems; don't fix them in this task.
- Credentials are temporary. On `ExpiredToken`, stop and ask for fresh ones. Never write
  credentials, the account ID or ARNs into any file.
- The API allows 5 requests at once. Keep at most 3 in flight (`run_eval` uses 3), and don't run
  anything while someone is demoing the live site.
- Evaluation traffic must be marked `"source": "eval"` (run_eval does this), so the admin page
  keeps it apart from real users.
- Set `ASKWRI_API_URL` from `terraform -chdir=infra output -raw api_url`. The API key is read from
  Secrets Manager (`askwri/api-key`) by the runner; never print it.

## What exists

| Piece | Where | What it does |
|---|---|---|
| Test set | `eval/testset.jsonl` | 30 questions: factual 8, method 4, decision 5, partnerships 3, old-document 2, cross-language 3, synthesis 2, unanswerable 3. Generated from the corpus (`generated: true`); each has expected sources (doc_id, pdf_page), must-include facts, expected reader and language. |
| Answer evaluation | `uv run python -m eval.run_eval run --configuration "<label>"` | Asks every question through the deployed API; scores recall@5, precision@5, page hit, must-include, figures cited, verified rate, decline accuracy, reader, language, latency, cost. Saves `eval/results/<run_id>.json`, uploads to `s3://askwri-corpus-<account>/eval/results/`, sends `AskWRI/Eval` metrics. The newest run is the admin page's scorecard. |
| AgentCore judges | `uv run python -m eval.run_eval judge <run_id>` | AgentCore batch evaluation with Builtin Correctness, Faithfulness, Helpfulness, ResponseRelevance and Refusal, using the test set's facts as assertions. Wait 5 minutes after a run (spans need to arrive). Results in the run file and the AgentCore console. |
| Retrieval evaluation (Jay) | `uv run python -m evals.run <label>` | 16 questions, a model judges each retrieved passage (helps / related / no). Measures search alone, not answers. |
| Dashboards | CloudWatch `askwri-quality`; admin page `/admin/` | Scorecard and live cost, speed and quality. |

Earlier runs to compare against: `20261105-002749` (first run), `20261105-004726` (first judged
run: Correctness 0.93, ResponseRelevance 0.94, Helpfulness 0.74, Faithfulness 0.71) and
`20261105-024707` (teammate, 26 questions). A baseline run on the reloaded corpus (Jay's latest
pipeline, all 580 documents) is queued as "askwri-cognito: Jay's latest pipeline…": use it as
the baseline if it has finished, rather than repeating it.

## Targets

From WRI's brief: every claim cited (100%), the right source in the top 5 (recall@5 at least
75%), every unanswerable question declined, a useful source in under a minute. Ours on top:

| Metric | Target |
|---|---|
| Figures cited rate | 100% |
| Recall@5 | ≥ 75% |
| Precision@5 | report only |
| Unanswerable / false-premise declined | 100% |
| Answerable questions wrongly declined | ≤ 5% |
| Verified rate (claims kept after checking) | ≥ 90% |
| AgentCore Faithfulness | ≥ 0.80 |
| AgentCore Correctness | ≥ 0.85 |
| Reader (audience) inferred correctly | ≥ 90% |
| Answer language matches the question | 100% |
| Median time, Quick / Deep | < 20 s / < 45 s; p90 < 60 s |
| Estimated cost per answer | report only |

## 1. Baseline on the current system

1. Run the full test set: `run --configuration "askwri-cognito baseline"`, then `judge`.
2. Compare every metric with the three earlier runs and the targets. Break results down by
   category (the run file has `by_category`).
3. For each failure, record the question ID, what went wrong (wrong source, missing fact,
   unsupported claim, wrong decline, slow) and one line of evidence.
4. Look into Faithfulness first (the lowest judged score): in the AgentCore batch evaluation,
   read the lowest-scoring sessions' explanations and list which sentences the judge found
   unsupported.

## 2. Search alone

Run Jay's retrieval evaluation (`evals.run askwri-cognito`) and compare with his saved runs. It
checks the search rules now live: reference and contents passages are skipped, "published in
2025" becomes a year filter, at most 6 passages per document.

## 3. Feature checks (new items, 3 to 5 questions each unless stated)

Write these as extra lines in a new file (`eval/testset-features.jsonl`, same fields) and run
with `--testset`. Check from the run file, and from askwri-db where noted (read-only, through
the RDS Data API).

| Feature | Questions | Pass when |
|---|---|---|
| Topic spaces | 2 per topic (22), sent with `filters.topic` = the topic | every source's document has that topic (`documents.topics` or `topic`); a question with nothing in the space declines |
| Year rule | "What did WRI publish in 2025 on …?" | every source's document year is 2025 |
| Apparatus skipped | any 10 answerable questions | no source chunk has a `role` (look up `chunks.role` by `chunkId`) |
| Figures and charts | questions only a chart answers (find them from `chunks` where `kind` is 'chart' and the description is specific) | a chart or image chunk is among the sources; the answer never quotes its description word for word |
| Quick answer widening | 5 broad, multi-part questions | answered, not declined; when `widened` is true, more than half the claims verified |
| False premise | 5 questions that assume a conclusion WRI didn't reach | declined |
| Cross-language | 2 each in es, fr, pt, id | answer language matches; every number in the answer appears in the cited English passages |
| Reader inference | 3 per reader (researcher, policymaker, partnerships), no reader set | `audience` matches |
| Summary | any 10 answers | summary present, every sentence carries a marker, each marker's source is in the sources list |
| Fact-check (mode `factcheck`) | 5 drafts mixing true, wrong and unsupported claims | each claim's verdict matches the expected one (record expected verdicts in the file) |
| Report formats (mode `deep`) | the same topic as summary, issue brief and talking points | the three differ in structure (talking points: short single sentences) |
| Topic dossier (deep, format `dossier`) | 3 topics | evidence matrix, agree / differ points (each citing 2+ papers) and gaps present |

## 4. Citation links

Sample 30 rows from the `citations` table (rebuilt on the new corpus). For each, judge with a
model or by hand: does the context sentence really mention the target document, and is the
relation label (extends, supports, contrasts, updates, uses data or method, background) right?
Report precision of the link and accuracy of the label.

## 5. Speed, load and access

- Latency: from the baseline run, median and p90 for Quick and Deep, and time to the first
  source found.
- Load: 5 questions at once on different sessions; all must answer, with latency no worse than
  1.5× single. Then 8 at once, and report what the extra ones get (throttling is expected).
- Access: no token → 401; a forged token → 401; a signed-in non-admin on `/admin/overview` →
  403; the hosted origin passes CORS. Use the server key only for the eval runner.

## What to hand back

- The run IDs (they show on the admin page) and the AgentCore batch evaluation IDs.
- One table: every metric above, this run against the targets and the earlier runs, and
  On target / Below target for each.
- The failures list from part 1 and the feature-check results from part 3, each with the
  question, the expected and the actual outcome.
- The three most important things to fix, with the evidence for each.
- The new test files committed on a new branch (`askwri-eval-features`); results stay out of git
  (`eval/results/` is ignored).
