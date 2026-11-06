# AskWRI: project overview

What we built for the World Resources Institute, the strategies behind it, the decisions we
made and why, how well it works, and what we learned. For using it, see the
[user guide](../USER-GUIDE.md); for deploying it, [REPRODUCE.md](REPRODUCE.md).

## In one paragraph

AskWRI is an agentic research assistant over 580 WRI publications. A single agent on Amazon
Bedrock AgentCore plans its searches, searches a hybrid vector and keyword index in Aurora
PostgreSQL through tools on AgentCore Gateway, drafts an answer with Claude, and verifies every
claim twice (its own claim check, then Bedrock Guardrails' grounding check) before anything is
shown. Every sentence links to the exact PDF page. It declines when WRI's research doesn't
answer the question, writes for whoever is asking, fact-checks drafts, searches inside charts
and maps, and answers in four languages. Quality is measured on every release with a 30-question
test set and AgentCore's built-in LLM judges, and shown on an admin page with live cost.

## What WRI asked for, and what we delivered

From WRI's vision document:

| WRI's requirement | Priority | What we built |
|---|---|---|
| Corpus ingestion (50–150 documents) | Must Have | 580 publications from 727 PDFs, with page numbers, tables, charts and rich labels |
| Cited Q&A, grounded only in the corpus | Must Have | Every claim cited to a passage and page, checked twice, unsupported text removed |
| "No answer" response | Must Have | Declines below a measured evidence threshold, after widening the search; shows what was searched and the closest work |
| Research briefing | Must Have | Deep research: parallel sub-questions, report formats (summary, issue brief, evidence matrix, evidence-to-action), topic dossier |
| Simple UI | Must Have | Hosted web app with sign-in, streaming steps, PDF side panel, spaces, filters, visuals |
| Translation | Should Have | Spanish, Portuguese, Bahasa Indonesia; numbers checked to survive; sources kept in the original |
| Research suggestions | Should Have | "What the evidence can't tell you", where reports disagree, and the closest related WRI work when it declines |
| Figure and table parsing | Should Have | 3,463 tables kept as tables with summaries; 2,289 charts, maps and images described by a vision model |
| Multi-agent workflow | Optional | Deliberately not built: one agent with parallel calls (see decisions) |
| Definition of done | — | Every answer cited; unanswerable questions declined (3 of 3); deployed and reproducible with Terraform |

Beyond the brief: fact-check a draft, research lens, citation map between reports, topic spaces,
region/year/type filters, follow-up memory, reader inference, invite-only sign-in, an admin
page with evaluation and cost, and AgentCore Evaluations.

## Strategies

**1. Trust before fluency.** The product is only useful if nothing invented reaches the reader.
So the agent may use only retrieved passages and cites them by ID; each claim is checked against
its own passage (quotes must be in it, numbers must appear in it); Bedrock Guardrails then
scores grounding; anything that fails is removed. Chart descriptions and model-written summaries
are used to *find* evidence but are never quoted as evidence. When too little survives, the
answer becomes a decline.

**2. Get the data right first.** Most wrong answers trace back to the documents. The pipeline
keeps reading order, tables and both page numbers, audits every passage against the PDF's own
text (a passage with words that aren't on the page fails the document), marks references,
contents and acknowledgements so search skips them, and labels each document from wri.org first
(year coverage went from 232 to 573 documents). Loading is resumable and transactional.

**3. Agentic retrieval, not one-shot RAG.** The agent plans queries, judges whether the evidence
is strong enough (best rerank score against a measured threshold), rewrites and widens the
search when it isn't, and only then answers or declines. Deep research splits a topic into
sub-questions searched in parallel.

**4. One agent, parallel calls.** A single agent is easier to verify, cheaper and faster than
coordinating several. Parallel model calls inside one step (sub-questions, one per paper in a
matrix, claim checks) give the speed.

**5. Measure everything.** A test set built backwards from real passages gives objective scores
(right report, right page, required facts, correct declines). AgentCore's judges add an
independent view. Every question is logged with time, tokens, cost and claims removed, and the
admin page shows it all against targets.

**6. Small models where they're enough.** Claude Sonnet writes and reads charts; Claude Haiku
plans, labels and checks. That keeps an answer around five cents.

**7. Managed and serverless.** AgentCore, Lambda, Aurora Serverless (pauses when idle), S3 and
CloudFront: nothing to patch, and cost close to zero when nobody is using it.

## Key decisions

| Decision | What we chose | Why | What we turned down |
|---|---|---|---|
| Retrieval | Our own search on Aurora PostgreSQL + pgvector | Page-exact citations, skipping supporting material, tables and charts as items, filters, at most 6 passages per report | Bedrock Knowledge Bases: less control over chunks, filters and citations |
| Search method | Vectors + keywords, reciprocal rank fusion, best 30 reranked with Amazon Rerank | Vectors find paraphrases; keywords catch names, acronyms and numbers; reranking puts the answering passage first | Vectors alone |
| Embeddings | Cohere Embed v4, 1,024 dimensions | Multilingual: a Spanish question finds English passages | Titan Text Embeddings v2 (first version) |
| Database access | RDS Data API with IAM sign-in | No network path or passwords for the tools; least privilege | Direct connections with app passwords |
| Agent framework | A short hand-written loop | The order of steps (search, draft, verify, decline) is the product, and every step is visible in traces | Strands Agents, LangChain |
| Agent count | One agent | Simpler to verify and cheaper; the hackathon's expert advised that multi-agent wasn't needed | Multi-agent orchestration |
| Agent hosting | AgentCore Runtime, Gateway (MCP), Memory, Observability, Evaluations | Isolated session per chat, secured tools, follow-ups, traces and judges, all managed | Our own container or Lambda |
| Verification | Claim check + Guardrails grounding (threshold 0.5) | Two independent checks | Guardrails' relevance filter: it scored good key points against the whole question and removed them |
| Decline rule | Best rerank score below 0.01 after widening | Measured: answerable 0.018–0.993, unanswerable at most 0.002 | A guessed 0.5-style threshold |
| Summary | Written in the same model call as the answer | A separate call added 2–4 s (Quick answer ~16 s → ~13 s) | A second summary call |
| API | Lambda Function URL with response streaming | Deep research can exceed API Gateway's 30 s limit; steps stream live | API Gateway HTTP API |
| Web | Static Next.js on private S3 behind CloudFront | No servers, fast, cheap | Server-rendered hosting |
| Sign-in | Cognito, invite only, PKCE; API verifies each token; admin group | No shared key in the browser | A shared API key |
| Usage log | DynamoDB, one row per question | Feeds cost, latency and quality on the admin page | Parsing logs at read time |
| Infrastructure | Terraform for everything, one account, us-west-2 | Repeatable; WRI could deploy it in its own account | Console changes |

More detail: [askwri-solution-design.md](askwri-solution-design.md) and the task notes in
[tasks/](tasks/).

## Results and how we measured them

**Test set.** 30 questions written backwards from real WRI passages (factual, methods,
decisions, partnerships, older reports, other languages, synthesis), each with the report and
page the answer should cite, the facts it must contain, the reader and the language, plus 3
hand-written questions WRI's research doesn't answer. `eval/run_eval.py run` asks them all
through the deployed API; `judge` runs AgentCore Evaluations' built-in judges on the same traces.

Official run `20261105-050756`:

| Measure | Result | Target |
|---|---|---|
| Answers with every figure cited | 100% | 100% |
| Expected report among the first 5 cited (recall@5) | 92% | ≥ 75% |
| Precision@5 | 67% | monitored |
| Out-of-scope questions declined | 3 of 3 | all |
| Claims kept after verification | 90% | — |
| Reader inferred correctly | 96% | — |
| Judges: relevance · correctness · faithfulness · helpfulness | 0.97 · 0.88 · 0.82 · 0.72 | — |
| Median time, Quick · Deep | ~20 s · ~25 s | < 60 s |
| Cost per answer | about $0.05 | — |

**How to read these honestly:**

- Recall is measured on the answer's cited sources, and declined questions are left out. Counting
  the two wrongly declined answerable questions as misses, recall is about 85%.
- Precision reads low by construction: each question has one "correct" report, so an answer
  citing three good reports scores 33%.
- 30 questions is a seed set, partly model-written; WRI's own questions would make it stronger.
- Runs vary: which answerable questions get declined changes from run to run (see
  [HANDOFF.md](HANDOFF.md)).

## What was hard, and what we learned

- **Checking without slowing down.** Verification is most of the wait. Writing the summary in
  the draft call and running checks in parallel took Quick answers from about 16 s to 13 s.
- **Messy PDFs.** Reading order, tables split across pages, charts, reference lists. Early
  answers quoted bibliographies until supporting material was marked and skipped.
- **Broad questions.** "Environmental laws in Europe" scored too low against specific reports,
  so the Quick answer now splits a broad question and searches again before declining.
- **Rerank scores are small numbers.** Good matches can score 0.02; the decline threshold had to
  be measured, not guessed.
- **Guardrails' relevance filter misfired** on Deep research key points; we use grounding only.
- **Evaluation needs care too.** One "unanswerable" question became answerable once the full
  library was loaded; the system was right and the test was wrong. AgentCore's judges found no
  traces at first, because spans live in the runtime's log group.
- **Production details.** An ad blocker hid the admin page because its CSS classes started with
  `ad-`. AgentCore Memory has a size limit per event, which long reports hit.

## Timeline

| Day | Work |
|---|---|
| Nov 3 | Corpus sorting, layout-aware parsing, chunking, page numbers, citation audit, wri.org labels, model registry |
| Nov 4 | Network, Aurora + pgvector, tools and Gateway, the agent on AgentCore Runtime with Memory and Guardrails, streaming API, UI connected; follow-ups, evidence-aware citations |
| Nov 5 | Full library loaded with tables, figures and richer labels; citation links, visuals, Explore; fact-check, lens, dossier; Cognito sign-in, hosting on CloudFront, admin page; evaluation and AgentCore judges; spaces, filters, demo chats, user guide |

## Team

Team DefinitelyNotAI. The ingestion pipeline (`askwri/ingest/`, search tuning and the
search evaluation in `evals/`) was built by Jay Parmar (@jayparmar16); the agent, tools, AWS
infrastructure, API, UI, admin page and end-to-end evaluation were built by the rest of the
team. Task-level ownership and decisions are recorded in [tasks/](tasks/).
