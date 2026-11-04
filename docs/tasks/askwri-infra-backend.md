# AskWRI infrastructure and backend

Owner: AlekyaKowta
Status: in-progress
Spec: docs/askwri-solution-design.md ("AWS deployment layout" and "Implementation runbook")

## Goal

Deploy the AskWRI backend into the team sandbox account (us-west-2) with Terraform, following
the design doc's runbook phases 1 to 6 (no UI, no voice): network and Aurora pgvector,
ingestion, the five gateway tools, the agent on AgentCore Runtime, the API, and evaluation.

## Done when

- [ ] Phase 1: `infra/` creates askwri-vpc, 4 private subnets, security groups, VPC endpoints
      (S3, bedrock-runtime, bedrock-agent-runtime, secretsmanager, logs), askwri-corpus,
      askwri-db with the Data API, the askwri/db secret and askwri-rg; `db/schema.sql` applied.
      State lives in S3 with `use_lockfile`; the provider refuses any other account.
- [ ] Phase 2: a PDF uploaded to raw/ fills `documents` and `chunks` with page numbers,
      doc_id (URL, else DOI, else SHA-256), date_source and date_confidence, tags and
      embeddings. Figure and table pages are described inline by the vision model.
      askwri-ingest has reserved concurrency 10 and a 900-second timeout. The largest sample
      PDF is ingested first and its duration reported; at 12 minutes or more, stop and
      decide whether to move ingestion to ECS Fargate.
- [ ] Phase 3: an MCP client with a Cognito token lists the 5 tools on askwri-gateway, and
      search returns cited passages (hybrid vector + full-text, reranked).
- [ ] Phase 4: askwri-agent-runtime returns cited answers in Quick answer and Deep research
      modes, declines unanswerable questions helpfully, and uses askwri-memory for follow-ups.
- [ ] Phase 5: the API (Lambda Function URL) returns chat answers within its timeout and a
      5-minute presigned source download.
- [ ] Phase 6: the eval script scores the test set per mode and pushes AskWRI/Quality metrics
      that show on the askwri-quality dashboard.
- [ ] README documents setup, deploy, check and destroy steps; no account ID, ARN or secret
      is committed.

## Decisions

- Follow the design doc where it disagrees with issues #2 and #10-13 (Terraform, own
  tables, Lambda ingestion, multilingual); those issues are to be edited later.
- Ingestion is one Lambda per PDF, triggered by S3 events on raw/ (not the Fargate task of
  #13). Reserved concurrency 10 keeps bulk uploads within Aurora's connection limit and
  Bedrock's request limits; the 15-minute Lambda limit is checked on the largest PDF.
- Lambdas sign in to Aurora with IAM database authentication as askwri_ingest or
  askwri_tools; the askwri/db master secret is used only by the Data API.
- Retrieval is plain SQL with psycopg, not LlamaIndex: it keeps the doc's schema.sql.
- The agent loop is hand-written on `askwri.models.call_claude`, not Strands.
- Figure and table pages are described inline in the ingestion Lambda, not by a Bedrock
  batch job (batch jobs need a minimum record count).
- The API is a Lambda Function URL, not an API Gateway HTTP API, because Deep research can
  take longer than the HTTP API's 30-second limit.

## Handoff

None yet.
