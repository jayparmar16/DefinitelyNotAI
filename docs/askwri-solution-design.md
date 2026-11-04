# AskWRI Solution Design

Nov 3, 2026 · @Alekya

## Executive summary

We are building AskWRI as a single tool-using agent with self-correcting retrieval over a sample of WRI research, on Amazon Bedrock and AgentCore. Every claim is cited to a WRI passage, unsupported claims are removed before output, and weak evidence produces a helpful decline. Multi-agent is built as an optional Day 2 upgrade, never a dependency for the Must Haves.

**Pitch:** AskWRI doesn't just retrieve. It protects WRI's institutional memory: it knows which evidence is strongest, catches outdated or conflicting WRI figures, connects researchers to the people behind the work, and works across languages and offices.

**Key decisions**

| Decision | Choice | Why |
| --- | --- | --- |
| Agent architecture | Single agent + agentic RAG loop; multi-agent as optional upgrade | Accuracy comes from retrieval; lowest risk to Must Haves; lowest cost |
| Retrieval store | Aurora PostgreSQL Serverless v2 with pgvector + full-text search | WRI's stated preference; hybrid search in one database; scales down when idle |
| Agent runtime | Bedrock AgentCore Runtime, Gateway, Memory, Observability | Customer direction; pay per use |
| Models | Small model for routing, evaluation and verification; larger model only for final synthesis | Cost control without losing answer quality |
| Grounding | Claim-level passage IDs + Bedrock Guardrails contextual grounding check | Meets the 100% citation requirement |
| Evaluation | 20-question test set, ablation of three configurations | Proves where accuracy and cost come from |

## What WRI wants

WRI wants a research assistant whose every answer traces to a specific WRI source, so 50 years of research stops being underused.

**The problem.** Researchers find prior work through site search, a database that only covers 2019 onward, and asking senior staff. Older publications without DOIs get missed, staff can't see what WRI already covered, and research in other languages is hard to use. Generic chatbots don't help because their answers can't be verified.

**Users**

| User | Primary need |
| --- | --- |
| Researchers (junior and senior) | Find and cite relevant WRI work quickly |
| Partnerships / Fundraising | Short, cited briefings on a topic |
| Global office staff | Access research in any language |
| WRI Data Lab | A pattern they can bring back into their own environment |

**Hard constraints:** every claim cites a WRI source; answers use only WRI's published research, not the web; public documents only; empty AWS sandbox; 2 days.

**Success metrics**

| Metric | Target | How we measure it |
| --- | --- | --- |
| Citation traceability | 100% of claims cited | Claim-level check on every demo answer |
| Retrieval recall | Report on 15-25 questions (prototype target 75%) | recall@5 against expected sources |
| Time to useful source | Under 1 minute | Latency logged per query, timed demo |

**What their context tells us.** WRI publishes seven product types (reports, issue briefs, guidebooks, working papers, technical notes, practice notes, expert notes) with different evidential weight. "Institutionally coherent" is one of WRI's formal research standards. The Data Lab has publicly said it wants domain-specific research agents with safeguards, and "generative documents" tuned to the reader.

## Architecture decision: single agent with agentic RAG

We build one tool-using agent with a self-correcting retrieval loop, and treat multi-agent as an optional upgrade that is ready but never required.

| Option | Accuracy | Cost per query | Risk to Must Haves | Verdict |
| --- | --- | --- | --- | --- |
| Plain RAG (retrieve once) | Limited by first retrieval | Lowest | Low | Too weak: misses old documents and multi-part questions |
| Single agent + agentic RAG | High: retrieval is re-checked and retried | Low (2-4 model calls) | Low | **Chosen** |
| Full multi-agent | Similar on Q&A, slightly better on broad briefings | High: each agent re-reads context | High: "multi-agent setup takes too long" is in WRI's own risk table | Optional Day 2 upgrade |

**Why single agent wins here**

- Two of the three success metrics (citation traceability, recall) are retrieval problems. More agents on bad passages give wrong answers at higher cost.
- Every Must Have can be delivered by one agent plus deterministic steps.
- Multi-agent is listed as Optional in the vision document.

**Upgrade path to multi-agent (Day 2, only if Must Haves are done)**

1. All tools already live behind AgentCore Gateway, so new agents reuse them unchanged.
2. Verification and briefing sub-research are written as separate functions with their own prompts.
3. Promote them into a Verifier agent and parallel Briefing worker agents.
4. Run the evaluation with and without them, and show quality vs cost side by side.

## Two modes: Quick answer and Deep research

The UI has one search box with a Deep research toggle: Quick answer is the cheap, fast default, and Deep research is the opt-in mode that carries the unique features.

**Why this works**

- **It matches cost to need.** Most questions take the cheap path; the expensive path runs only when a user asks for it. That is the nonprofit cost story made visible in the product.
- **It keeps the Must Haves safe.** Quick answer alone covers cited Q&A and the "no answer" response, so it can be finished and hardened on Day 1.
- **It makes the differentiators demonstrable.** Judges can see the same question answered both ways.
- **It gives the optional multi-agent feature a natural home.** If built, parallel workers run only in Deep research.

|  | Quick answer (default) | Deep research (toggle) |
| --- | --- | --- |
| Use for | A specific question | A topic, a briefing, a landscape or gap question |
| Retrieval | Hybrid search + rerank; one retry only if evidence is weak | Full self-correcting loop, up to 3 rounds, era-aware rewriting, sub-questions |
| Output | Short answer, sentence-level citations, authors | Structured report: summary, key findings with citations, change over time, outdated-figure flags, gaps, related publications, people to ask, suggested follow-ups |
| Audience format | Not applicable | Researcher summary, policymaker issue brief or partnership talking points |
| Verification | Same claim-level check + Guardrails | Same claim-level check + Guardrails |
| Decline | Helpful decline listing the nearest related WRI work | Helpful decline listing what was searched |
| Target time | Under 10 seconds | Under 1 minute, with first sources streamed early |
| Models | Small model for routing; larger model for the final answer only | Small model for sub-research; larger model for synthesis |

**Recommended refinements**

1. **Never lower the bar in Quick answer.** Citations, verification and the decline path are identical in both modes; only the depth of search changes.
2. **Show progress live in Deep research.** Stream the steps ("planning 4 sub-questions", "round 2: adding pre-2010 terms", "verifying 18 claims") and show sources as they are found. This keeps time-to-first-source under a minute and makes the agent's work visible.
3. **Carry context between modes.** A follow-up after Deep research ("now in Spanish", "make it talking points") reuses the gathered evidence through AgentCore Memory instead of searching again.
4. **Make the report shareable.** Download as Markdown or PDF with citations intact, since partnership staff want something to send (see Citations, sources and downloads).
5. **Measure both modes separately.** The evaluation reports recall, citation precision, latency and cost per query for each mode, and the quality dashboard shows them side by side.

Two refinements are moved to the Backlog: a "Run Deep research" suggestion button and expected-time text on the toggle.

**Implementation:** one AgentCore Runtime agent with a `mode` parameter. Quick answer runs plan (light), retrieve, draft and verify; Deep research runs the full loop plus the coverage, outdated-figure, authors and briefing steps. Both use the same Gateway tools, so there is no duplicate code.

## Citations, sources and downloads

Every answer ends with a sources list like a chatbot, and every source can be opened at the cited page or downloaded.

**What the user sees**

- **Inline markers** \[1\], \[2\] on each sentence, linked to the sources list.
- **Citation card per source:** title, publication type, year, office, authors, page, and the quoted passage highlighted.
- **Buttons on each card:**
  - Open at page: the wri.org PDF link with `#page=N`.
  - Download PDF: a short-lived download link to our stored copy.
  - Copy citation: a formatted reference (title, WRI, year, URL, DOI when present).
- **Download the whole answer or report:** Markdown or PDF, with inline markers and the full sources list; plus a sources-only file (CSV or BibTeX) for reference managers.

**How it works and where it lives**

| Piece | Implementation | AWS resource and placement | Check |
| --- | --- | --- | --- |
| Source metadata in the answer | Agent returns structured JSON: answer text with markers + sources array (doc\_id, title, type, year, page, passage, url, doi) | AgentCore Runtime askwri-agent-runtime | Every marker maps to one source entry |
| Open at page | Link to the original wri.org URL with a page anchor | None (public WRI site) | Link opens the right page |
| Download PDF | API route `GET /sources/{doc_id}/download` returns an S3 presigned URL valid for 5 minutes | askwri-api Lambda (outside VPC); askwri-api-role gets s3:GetObject on askwri-corpus raw/\* only | URL downloads the file; expires after 5 minutes; bucket still private |
| Export answer or report | Client-side Markdown and PDF generation in the browser | None (runs in the UI) | Exported file keeps markers and sources |
| Sources file | CSV or BibTeX generated from the sources array | None (runs in the UI) | Imports into a reference manager |

The stored copy exists because the bucket is private and encrypted; presigned URLs give access without making anything public. Keep the wri.org link as the primary "Open" action so users land on WRI's own site.

## UI design: WRI Design System and source viewer

We build the UI with WRI's own open-source Design System, so AskWRI looks and behaves like a WRI product from day one.

**WRI Design System**

- Package: `@worldresources/wri-design-systems` ("WRI UI Library"), open on GitHub (wri/wri-design-systems), documented on Zeroheight, built on Chakra UI.
- Requirements listed in its README: Node 22.14.0, React 19, plus `@chakra-ui/react` and `@emotion/react`.
- It is AI-native: `ds setup-ai` configures context files and an MCP integration for coding assistants such as GitHub Copilot, so generated UI uses WRI components and tokens.
- Use its containers, data display, forms, tags, navigation and status components for the chat, citation cards, toggle and report view.

**Checks:** confirm the Design System installs cleanly in our Next.js app with the React version we use; confirm its license on GitHub; ask the Data Lab whether they want AskWRI themed with the default WRI colors.

**Layout**

| Area | Contents |
| --- | --- |
| Main column | Search box with Deep research toggle; answer with inline markers; sources list with citation cards |
| Side panel | Report view (Deep research) or source viewer (below); resizable, closable |
| Header | Language selector, audience selector (Deep research), download menu |

**Optional feature: interactive source viewer in the side panel**

Clicking a citation opens the source PDF in a side panel, scrolled to the cited page with the passage highlighted, similar to a document side panel in a chat app.

- Built with PDF.js (for example react-pdf); loads the file through the presigned download URL, so no extra AWS resources are needed.
- Highlights the passage by searching the page's text layer for the quoted text.
- Tabs in the side panel switch between the report and open sources; previous and next buttons step through citations.
- Check: highlighting works on text-based PDFs; scanned PDFs fall back to opening at the page without a highlight.

## System architecture

A request flows from the UI through a FastAPI backend into one AgentCore agent, which plans, retrieves, checks its own evidence, drafts with citations and verifies before answering.

&#91;embedded content: AskWRI architecture · request path, agent loop, ingestion\]

The agent loops back to planning when any sub-question lacks strong evidence, up to three rounds; if evidence is still weak, the output is a helpful decline.

**Agent tools (behind AgentCore Gateway)**

| Tool | What it does |
| --- | --- |
| search(query, filters) | Hybrid vector + keyword search in Aurora, filtered by year, type, program, country, language; reranked |
| get\_passage(chunk\_id) | Returns full passage text, page and document metadata for citation |
| coverage(dimensions) | Counts documents by topic, country, program, year, language for gap analysis |
| authors(doc\_ids) | Returns public authors of cited documents |
| translate(text, lang) | Bedrock translation with number-preservation check and cache |

## Framework choices

We use LlamaIndex for ingestion and retrieval, because it is in WRI's own stack, and write the agent loop as explicit steps so our differentiators stay under our control.

| Layer | Framework | Why |
| --- | --- | --- |
| Ingestion | LlamaIndex readers and node parsers, with PyMuPDF for page-level extraction | Page number and metadata attached to every chunk |
| Retrieval | LlamaIndex Postgres vector store in hybrid mode (pgvector + Postgres full-text) on Aurora, Bedrock embeddings, Bedrock reranker | Hybrid search with metadata filters and little custom code; portable to WRI's LlamaIndex services |
| Agent loop | Strands Agents (AWS's open-source agent SDK) or LlamaIndex Workflows; pick whichever the team knows | AgentCore Runtime runs any Python framework; Strands has the most AgentCore examples |
| Tools | Python Lambda functions exposed through AgentCore Gateway as MCP | Framework-independent; callable by other WRI products |
| API | FastAPI | Matches WRI's search service |
| UI | Next.js | Matches WRI's frontend experience |

**Rule for the agent loop:** plan, retrieve, evaluate, retry and verify are explicit functions we write, not a generic prebuilt agent class. That is what enforces the 3-round cap, era-aware rewriting and claim-level verification, and it is what produces the reasoning trace shown in the UI.

## AWS services map

Every component runs on serverless or pay-per-use AWS services, so the system costs almost nothing when idle.

| Layer | Component | AWS service | Why this choice |
| --- | --- | --- | --- |
| Storage | Raw PDFs, extracted text, page images | Amazon S3 (private, SSE encrypted) | Required by WRI's security basics; cheap |
| Ingestion | PDF text extraction, chunking, metadata tagging | AWS Lambda (Python 3.12) or an ECS Fargate task for long PDFs | Serverless first; Fargate mirrors WRI's services if Lambda limits are hit |
| Ingestion | Figure and table pages | Bedrock vision-capable model via batch inference | Only pages flagged as having tables or figures; batch is lower cost |
| Embeddings | Multilingual passage embeddings | Bedrock embedding model (multilingual, e.g. Cohere Embed Multilingual or Titan Text Embeddings v2) | Cross-language retrieval without translating the corpus |
| Retrieval | Hybrid search (vector + BM25-style full text) | Amazon Aurora PostgreSQL Serverless v2 with pgvector + tsvector | WRI's preferred pattern; one database for both; scales down when idle |
| Retrieval | Reranking top 20-30 passages | Bedrock rerank model | Cheapest accuracy gain |
| Agent | Agent loop and orchestration | Amazon Bedrock AgentCore Runtime | Customer direction; serverless agent hosting |
| Agent | Tools (search, get\_passage, coverage, translate, authors) | AgentCore Gateway (tools exposed as MCP) | Reusable by future agents and by other WRI products |
| Agent | Conversation context, follow-ups | AgentCore Memory (short-term) | Follow-up questions and "now in Spanish" requests |
| Models | Router, retrieval evaluation, verification | Small Bedrock model (Haiku-class) | Low cost per call |
| Models | Final answer and briefing synthesis | Larger Bedrock model (Sonnet-class) | Quality where it shows; cross-region inference if not in the sandbox region |
| Grounding | Contextual grounding check | Amazon Bedrock Guardrails | Out-of-the-box hallucination gate |
| Observability | Traces, tokens, latency per step | AgentCore Observability + Amazon CloudWatch | Feeds the cost-per-query and loop-rounds metrics |
| API | Backend API | FastAPI on Lambda (via Lambda Web Adapter) or API Gateway + Lambda | Matches WRI's Python/FastAPI stack |
| UI | Chat and briefing interface | Next.js static export on S3 + CloudFront (or AWS Amplify Hosting) | Matches WRI's TypeScript/Next.js experience |
| Security | Roles, secrets | IAM least-privilege roles, AWS Secrets Manager | WRI's security basics |
| Infrastructure | Reproducible deployment | Terraform | WRI's IaC tool; satisfies "reproducible from the team repo" |

Not used on purpose: Amazon OpenSearch Serverless, because its standing minimum capacity charge would dominate a small nonprofit bill. Confirm model availability in the sandbox region on Day 1.

## AWS deployment layout

Everything runs in one region and one VPC with private subnets only and no NAT gateway; only the database, the tool Lambdas and ingestion sit inside the VPC.

**Placement principles**

- **Region:** the sandbox default region. Confirm on Day 1 that the chosen Bedrock models, AgentCore, and batch inference are available there; use a cross-region inference profile for any model that isn't.
- **Inside the VPC:** Aurora, the ingestion Lambda and the tool Lambdas, because they hold or touch the data.
- **Outside the VPC (managed, regional):** AgentCore Runtime, Gateway, Memory, Guardrails, the API, S3 and CloudFront. The agent never connects to the database directly; it only calls tools through Gateway.
- **No NAT gateway:** it bills hourly and isn't needed. AWS services are reached through VPC endpoints. WRI PDFs are uploaded to S3 from a laptop or CloudShell, not downloaded from inside the VPC.
- **Naming:** every resource starts with `askwri-`.

**Network**

| Item | Name | Value | Purpose |
| --- | --- | --- | --- |
| VPC | askwri-vpc | 10.20.0.0/16, DNS hostnames and DNS resolution on | Holds data-tier resources |
| Private app subnet A | askwri-app-a | 10.20.1.0/24, AZ a | Ingestion and tool Lambdas |
| Private app subnet B | askwri-app-b | 10.20.2.0/24, AZ b | Ingestion and tool Lambdas |
| Private DB subnet A | askwri-db-a | 10.20.11.0/24, AZ a | Aurora |
| Private DB subnet B | askwri-db-b | 10.20.12.0/24, AZ b | Aurora (a DB subnet group needs 2 AZs) |
| DB subnet group | askwri-db-subnets | askwri-db-a + askwri-db-b | Aurora placement |
| Route tables | askwri-rt-private | Local route only, plus S3 gateway endpoint | No internet route |

**Security groups**

| Security group | Inbound | Outbound | Attached to |
| --- | --- | --- | --- |
| askwri-sg-lambda | None | TCP 5432 to askwri-sg-db; TCP 443 to askwri-sg-endpoints; S3 prefix list on 443 | Ingestion and tool Lambdas |
| askwri-sg-db | TCP 5432 from askwri-sg-lambda only | None needed | Aurora cluster |
| askwri-sg-endpoints | TCP 443 from askwri-sg-lambda | None needed | Interface VPC endpoints |

**VPC endpoints**

| Endpoint | Type | Why |
| --- | --- | --- |
| com.amazonaws.\<region>.s3 | Gateway (free) | Lambdas read PDFs and write extracted text |
| com.amazonaws.\<region>.bedrock-runtime | Interface, both app subnets | Embeddings for queries, reranking, translation, tagging |
| com.amazonaws.\<region>.secretsmanager | Interface, both app subnets | Lambdas read the database secret |
| com.amazonaws.\<region>.logs | Interface, both app subnets | Lambda logs to CloudWatch |

Interface endpoints bill per hour per AZ, so delete them with `terraform destroy` after the event.

**Every resource: where it lives, who can access it, and how to check it**

| Resource | Name | Placement | Access (IAM role / policy) | Check |
| --- | --- | --- | --- | --- |
| S3 corpus bucket | askwri-corpus-\<account-id> | Region; prefixes raw/, text/, batch-in/, batch-out/ | Block Public Access on; SSE encryption; bucket policy allows only askwri-ingest-role, askwri-tools-role, askwri-bedrock-batch-role | `aws s3api get-public-access-block` shows all four true; anonymous URL returns 403 |
| S3 UI bucket | askwri-ui-\<account-id> | Region | Private; read only by CloudFront Origin Access Control | Direct object URL returns 403; CloudFront URL loads |
| CloudFront | askwri-cdn | Global | Origin Access Control to askwri-ui bucket; HTTPS only | Site loads over HTTPS only |
| Aurora PostgreSQL Serverless v2 | askwri-db | askwri-db-subnets, askwri-sg-db; not publicly accessible; minimum capacity as low as the engine version allows | Master credentials in Secrets Manager; app user with read on chunks, write only for ingestion | `CREATE EXTENSION vector;` succeeds; "Publicly accessible: No"; capacity drops when idle |
| Secrets Manager secret | askwri/db | Region | Read by askwri-ingest-role and askwri-tools-role only | No credentials in code or Terraform state outputs |
| Ingestion Lambda | askwri-ingest | askwri-app-a/b, askwri-sg-lambda; triggered by S3 events on raw/ (one invocation per PDF); reserved concurrency 10, so Aurora connections and Bedrock request limits are never overwhelmed; timeout 15 minutes | askwri-ingest-role: S3 read raw/, write text/; Bedrock invoke on the embedding and tagging models; secret read; logs | One PDF uploaded produces chunk rows with page numbers in Aurora; the largest sample PDF finishes well under 15 minutes (if not, move ingestion to an ECS Fargate task) |
| Bedrock batch inference job | askwri-vision-batch | Regional, managed; reads batch-in/, writes batch-out/ | askwri-bedrock-batch-role: S3 read/write on those prefixes only | Chosen vision model supports batch in the region; a 5-page test job completes |
| Tool Lambdas | askwri-tool-search, askwri-tool-passage, askwri-tool-coverage, askwri-tool-authors, askwri-tool-translate | askwri-app-a/b, askwri-sg-lambda | askwri-tools-role: secret read; Bedrock invoke on embedding, rerank and translation models; logs | Each returns results when invoked from the console with a test event |
| AgentCore Gateway | askwri-gateway | Regional, managed | Targets: the five tool Lambdas, invoked with askwri-gateway-role; inbound authorizer: Cognito client credentials (askwri-auth) | An MCP client lists the 5 tools and gets results |
| ECR repository | askwri-agent | Region | Push by deploy role; pull by AgentCore | Image pushed and scanned |
| AgentCore Runtime | askwri-agent-runtime | Regional, managed; public network mode is fine because data access goes through Gateway | askwri-agent-role: Bedrock invoke on the specific small and large models and the guardrail; Gateway invoke; Memory read/write; logs | Test invocation returns a cited answer |
| AgentCore Memory | askwri-memory | Regional, managed; short-term memory | askwri-agent-role | A follow-up ("now in Spanish") uses the previous answer |
| Bedrock Guardrail | askwri-guardrail | Regional; contextual grounding check enabled | Used by askwri-agent-role | An answer with an unsupported claim is blocked or flagged |
| API | askwri-api (FastAPI on Lambda) + askwri-http-api (API Gateway HTTP API) | Regional; outside the VPC | askwri-api-role: invoke askwri-agent-runtime only; CORS limited to the CloudFront domain; throttling on | UI can call it; other origins are rejected |
| Logs and traces | /askwri/\* log groups, AgentCore Observability | Region; 7-day retention | Read by the team | Token counts and latency visible per request |
| Resource group | askwri-rg | Region; tag query Project = AskWRI | Read by the team | Every resource above appears in the group |

**Gateway access resources**

Two separate permissions control the gateway. The Cognito authorizer decides who may call the gateway (our agent, or an MCP client with a token). The gateway role decides what the gateway may call: AWS services cannot invoke each other by default, so without askwri-gateway-role every tool call fails with access denied. It is limited to invoking the five tool functions.

| Resource | Name | Placement | Access | Check |
| --- | --- | --- | --- | --- |
| Gateway execution role | askwri-gateway-role | IAM (global) | lambda:InvokeFunction on the five askwri-tool-\* Lambdas only | Gateway can call each tool; it cannot call any other Lambda |
| Cognito user pool + app client | askwri-auth, app client askwri-gateway-client (client credentials grant, a custom scope such as askwri/search) | Regional | Client secret stored in Secrets Manager as askwri/gateway-client | A token request returns an access token; the gateway rejects calls without one |
| Agent's gateway token | AgentCore Identity outbound credential, or the agent reads askwri/gateway-client and requests a token | Managed | askwri-agent-role: read askwri/gateway-client | The agent lists and calls tools through the gateway |

Why Cognito instead of IAM: a gateway has one inbound authorizer, and the MCP tool demo (feature 10) uses outside MCP clients, which send tokens and cannot sign AWS requests. Each tool call adds one hop through the gateway; watch it in the latency traces.

**Tags (Terraform default\_tags on every resource)**

| Key | Value |
| --- | --- |
| Project | AskWRI |
| Environment | hackathon |
| Team | \<team name> |
| Owner | \<owner email> |
| ManagedBy | terraform |

Check: the askwri-rg resource group lists every resource, and Cost Explorer can filter by the Project tag (cost allocation tags may need activating; ask the sandbox admin).

Resources added by later sections (evaluation, quality dashboard, source downloads and voice) are listed with their placement and checks in those sections, and follow the same naming, tags and VPC rules.

## Data model and ingestion

We ingest 100-150 documents into page-level chunks carrying the metadata every differentiator depends on.

**Corpus sampling (deliberate, not random)**

- Weight toward older publications (pre-2019, no DOI), since WRI's current database starts in 2019.
- Include 5-10 non-English papers from WRI offices (WRI Brasil, WRI Mexico, WRI Indonesia).
- Cover all seven publication types, including a few technical notes linked to reports.
- Include at least one pair where a newer WRI publication revises an older estimate (needed for the outdated-figure demo).
- Concentrate on 2-3 programs (for example Cities, Climate, Forests) so gap analysis has enough density to mean something.

**Pipeline**

1. Download or receive PDFs into S3, with a manifest of title, URL and date.
2. Extract text page by page with PyMuPDF; flag pages with tables or figures.
3. Send only flagged pages to a vision model in a Bedrock batch job for table and figure descriptions.
4. Tag each document once with a small model: publication type, program, countries and regions, topics, authors, language (where not in the manifest).
5. Chunk by page (split long pages at \~500 tokens with overlap), keep page number.
6. Embed with the multilingual model and write to Aurora (vector + tsvector column).

**Chunk schema (Aurora table)**

| Field | Example | Used by |
| --- | --- | --- |
| doc\_id | wri.org URL, else the DOI, else the file's SHA-256 | Unique document ID (always present) |
| url | wri.org link or empty | Open at page |
| doi | 10.46830/... or empty | Shown when present; empty for older documents |
| file\_sha256 | Hash of the PDF | Duplicate detection |
| chunk\_id | doc42\_p7\_c1 | Citations (passage ID) |
| doc\_title | "Electric Buses in Latin America" | Citations |
| page | 7 | Deep link to PDF page |
| year, pub\_date | 2014, 2014-06-01 (or empty if undated) | Change over time, outdated figures, era-aware search |
| date\_source | manifest / printed / file\_metadata / none | Traceability of every date |
| date\_confidence | high / low / undated | Which features may use the date |
| pub\_type | Report / Working paper / Technical note | Evidence labels and ranking |
| office | WRI (global) / WRI Brasil / WRI Mexico | Cross-office discovery |
| program | Cities | Metadata filters, gap analysis |
| countries, regions | Colombia, Latin America | Gap analysis, filters |
| topics | electric mobility, public transport | Gap analysis |
| authors | List of names as printed | Finding the right person |
| language | es | Cross-language retrieval, translation |
| content | Page text or table description | Retrieval and grounding |
| embedding | vector | Semantic search |
| tsv | tsvector | Keyword search |

## Older documents and DOIs

Older WRI publications were never assigned DOIs, so we identify every document by its wri.org URL and treat the DOI as optional.

**Why there is nothing to look up.** WRI DOIs use the prefix 10.46830 and appear on recent publications, for example a 2020 working paper (10.46830/wriwp.20.00065) and 2023 technical notes. We could not confirm the exact start year, but older work generally has none. This is the gap WRI describes: publications without DOIs, plus a database that only covers 2019 onward, get missed.

**Where to get older documents**

| Source | How to use it | Note |
| --- | --- | --- |
| WRI's document dump (SharePoint link in the technical document) | Primary source; upload to the askwri-corpus bucket under raw/ | Check that it includes pre-2019 PDFs and a metadata file |
| wri.org research listing, sorted by date | Browse manually and record older PDF URLs | The site blocks automated access; do not build a crawler |
| World Resources Report series | Flagship reports back to the first edition in 1986 | Good source of old, high-value documents |

**How the design handles missing DOIs**

- `doc_id` rule: the wri.org URL if we have it, otherwise the DOI, otherwise a SHA-256 hash of the file (only for files with neither, such as bare PDFs in the dump with no metadata). The hash is stored for every file anyway, to catch the same PDF arriving twice from different sources. `url` and `doi` are separate optional fields.
- Citations show title, year, publication type, URL and page, so they work with or without a DOI.
- Era-aware query rewriting (feature 1) adds older terminology so old documents are found even when their wording differs from today's.
- The test set includes 2 questions only an old document can answer, plus 1-2 that only an undated or no-DOI document can answer.

**Dates: fixed rules, no model guessing.** No model reads pages to guess a date, ID or DOI. Ingestion takes the first date found, in this order, and stores year, date\_source and date\_confidence for every document:

1. The WRI dump's metadata file or our manifest (high confidence).
2. A printed date on the first or last 2 pages, found by pattern matching, such as "© 2009 World Resources Institute" or "Published May 2012" (high confidence).
3. The PDF file's own creation date (low confidence, since it is often the scan or upload date).
4. Nothing found: marked undated.

**How undated documents behave**

- Year filters mean "year ≥ X or undated", with an "Include undated" option that is on by default, so these documents are never hidden.
- Citations show "WRI, n.d.", or "c. 2009 (file date)" when the date has low confidence.
- Change-over-time and outdated-figure flags use only high-confidence dates. Undated documents are listed separately so they don't show up as gaps.

**Demo line:** WRI's current database starts in 2019 and DOIs start around 2020. AskWRI finds a 1990s report that neither one can.

## Must Haves: how each is implemented

All five Must Have features and all four Definition of Done items are covered by the single-agent design on Day 1 and Day 2 morning.

| Must Have | Implementation | AWS services | Done when |
| --- | --- | --- | --- |
| Corpus ingestion | Pipeline in the Data model section: page chunks, metadata, multilingual embeddings | S3, Lambda/Fargate, Bedrock embeddings, Aurora pgvector | 100+ documents searchable with full metadata |
| Cited Q&A | Agent loop with hybrid search, rerank, claim-level passage IDs; citation shows title, link to PDF page, quoted passage | AgentCore Runtime + Gateway, Aurora, Bedrock models | Every sentence in an answer carries a citation that opens the right page |
| "No answer" response | Decline when rerank scores are below a tuned threshold, or the loop ends without covering every sub-question, or Guardrails grounding fails. The decline says what was searched and lists the nearest related WRI work | Bedrock rerank, Bedrock Guardrails | All unanswerable test questions declined; no answerable ones wrongly declined |
| Research briefing | Fixed workflow: plan 3-5 sub-questions, retrieve for each in parallel, synthesize into summary, key findings, related publications; every claim cited | AgentCore Runtime, Bedrock models | A cited briefing in under 1 minute |
| Simple UI | One search box with a Deep research toggle; citation cards (title, type, year, page link, passage); report view; language and audience selectors; live progress trace | Next.js on S3 + CloudFront, FastAPI on Lambda | Demo runs end to end in the browser |

**Definition of Done checklist**

- [ ] All Must Have features demonstrated
- [ ] Every answer and briefing shows citations
- [ ] At least one unanswerable question is correctly declined
- [ ] Deployed in the sandbox and reproducible from the team repo (Terraform + README)

## Should Haves and Optional features

We implement all three Should Haves and the Optional multi-agent feature, in that priority order after the Must Haves.

**Translation (Should Have)**

- Retrieval across languages needs no translation: multilingual embeddings let an English query match Portuguese or Spanish passages directly.
- A `translate(text, target_lang)` tool on a Bedrock model translates answers, briefings or passages on request.
- Every translation is labelled "Machine-translated" and shown beside the original passage, as WRI's risk table asks.
- Citations always point to the original-language document, never to a translation.
- A deterministic check confirms every number, year and percentage in the original appears unchanged in the translation.
- Translations are cached, so repeat requests cost nothing.

**Research suggestions and gaps (Should Have)**

- Follow-up questions are generated from the retrieved evidence and labelled as suggestions.
- Gap analysis uses a `coverage` tool that computes document counts by topic, country, program, year and language from metadata. The agent explains the gaps; it does not invent them.
- Every gap answer states the corpus limit, for example "based on 120 sampled documents, not WRI's full library".

**Figure and table parsing (Should Have)**

- Only pages flagged as containing tables or figures go to a vision model, in a Bedrock batch job.
- The model's description is stored as its own chunk with the same page number, so it can be cited.

**Multi-agent workflow (Optional)**

- Built only if Must Haves are complete by Day 2 midday, using the upgrade path in the Architecture decision section.
- Verifier agent and parallel briefing worker agents reuse the same Gateway tools.

## Unique differentiators

We add ten features built for WRI's specific problems; most reuse metadata we already store, so they cost little to build.

| # | Feature | What the user sees | How it works | Effort | When |
| --- | --- | --- | --- | --- | --- |
| 1 | Self-correcting retrieval with era-aware rewriting | Better answers on hard and old-document questions; a trace like "searched 3 ways, round 2 added pre-2010 terms" | Plan sub-questions, retrieve, check each is covered (rerank scores + agent judgment), reformulate or filter and retry; max 3 rounds. Rewrites add period vocabulary ("global warming", older program names) | Medium | Day 1 |
| 2 | Claim-level verification before output | No uncited sentence ever reaches the user | Each claim must carry a passage ID; unsupported claims are dropped, then Guardrails grounding checks the whole answer | Low-Medium | Day 1 |
| 3 | Evidence-aware citations | Each citation shows publication type and year; working papers labelled "in progress"; findings traced to the technical note behind them | Small ranking boost by publication type; UI label from metadata | Very low | Day 1 |
| 4 | Finding the right person | "People who've published on this" beside the answer | Authors of cited documents, public authorship only | Very low | Day 1 |
| 5 | Helpful decline | Instead of a dead end: what was searched, why it wasn't enough, the nearest related WRI work | Decline path reuses retrieval results below the threshold | Low | Day 1 |
| 6 | Tailored briefings | Same evidence as an issue brief for policymakers, talking points for partnerships, or a technical summary | Three audience templates on one briefing workflow, matching WRI's own publication formats and the Data Lab's "generative documents" idea | Low | Day 2 AM |
| 7 | Discovery across offices and languages | An English question surfaces a WRI Brasil paper; briefing requested in Spanish | Multilingual embeddings + translate tool with number check | Low | Day 2 AM |
| 8 | Evidence-based gap analysis and change over time | "Strong work on X in Brazil, nothing after 2021 on Y in Colombia"; how WRI's view evolved 2005 to 2023 | Coverage tool computes counts by topic, country, year, language; agent explains them | Medium | Day 2 PM |
| 9 | Outdated and conflicting figure flags | "The 2014 report estimated X; the 2023 report revised it to Y. Cite the newer figure." | At answer time only, across retrieved passages: same metric, different years or programs, flag and prefer newer | Medium-High | Day 2 PM (stretch) |

**Feature 10: AskWRI as an MCP tool.** The search tools sit behind AgentCore Gateway as MCP, so any MCP client can use AskWRI's cited search without new integration code: Claude Desktop, GitHub Copilot, the MCP Inspector, or WRI's own internal tools and prototype. This matches the Data Lab's "headless" tools strategy and the way it already builds (its Design System is AI-native with an MCP integration), and it lets the Data Lab plug the same tools into its own environment instead of rebuilding them.

- **Cost:** almost nothing extra, because the tools are already Lambdas behind Gateway.
- **Authentication:** the gateway uses a Cognito client-credentials authorizer, because outside MCP clients send tokens and cannot sign AWS requests (see AWS deployment layout).
- **Demo (30 seconds):** connect the MCP Inspector or Claude Desktop to askwri-gateway with a token, run the search tool on a question, and show results with WRI citations. This proves AskWRI isn't locked inside its own UI.

**Also unique: an architecture justified by measurement.** We run the same test set across plain retrieval, hybrid plus rerank, the full agent loop and (if built) multi-agent, and report quality next to cost per query. WRI gets evidence for where agents pay off, plus a cost model for the full corpus.

**Also unique: number-safe translation.** A deterministic check confirms every number, year and percentage survives translation unchanged, since a mistranslated figure is the most damaging error for a research organization.

**Scoping note for feature 9.** No corpus-wide figure database. Before the event, find one real case in the sample where WRI revised an estimate, and make sure both documents are ingested. Without that, the feature can't be demonstrated.

## RAG evaluation plan

We evaluate on a 20-question test set across three configurations (plus multi-agent if built), so the results show exactly where accuracy and cost come from.

**Test set.** WRI may not supply ground truth (still an open question), so we build it by working backward: pick a passage, write the question it answers, record the expected document and page, and have a teammate verify each.

| Category | Count | What it proves |
| --- | --- | --- |
| Straightforward factual | 8 | Baseline recall |
| Multi-document synthesis | 4 | Briefing quality |
| Answerable only by an old document | 2 | Era-aware self-correcting loop |
| Cross-language | 2 | Multilingual retrieval and translation |
| Revised or conflicting figure | 1-2 | Outdated-figure flags |
| Unanswerable | 2-3 | Correct decline |

**Metrics**

| Metric | Definition | Target |
| --- | --- | --- |
| Retrieval recall@5 | Share of expected sources in the top 5 | 75% or better (prototype target) |
| Retrieval precision@5 | Share of top 5 that are relevant | Report |
| Citation precision | Share of cited passages that actually support their claim (model-judged, hand spot-checked) | 95% or better |
| Unsupported claims | Claims with no supporting passage | 0 |
| Decline accuracy | Unanswerable declined, answerable not declined | All correct |
| Latency | Time to answer | Under 1 minute |
| Retrieval rounds | Average loop rounds per query | Report |
| Cost per query | Tokens x model price, from traces | Report |

**Tooling.** A Python script computes recall and precision against the expected-sources file. RAGAS covers faithfulness and context precision and recall. Bedrock RAG evaluation jobs (model as judge) are an alternative if enabled in the sandbox. Token counts come from AgentCore Observability.

**Ablation (the headline results table)**

| Configuration | Recall@5 | Citation precision | Decline accuracy | Avg latency | Cost per query |
| --- | --- | --- | --- | --- | --- |
| A. Vector search, retrieve once |  |  |  |  |  |
| B. Hybrid search + rerank |  |  |  |  |  |
| C. Full agent loop + verification |  |  |  |  |  |
| D. Multi-agent (if built) |  |  |  |  |  |

Fill this table from real runs; never quote estimated numbers.

## Quality dashboard in AWS

Citation accuracy and retrieval quality are shown live in AWS through AgentCore Evaluations and a CloudWatch dashboard, so judges can see the numbers in the console, not just in slides.

**AgentCore Evaluations (managed).** It became generally available on March 31, 2026, in nine regions including US East (N. Virginia), US East (Ohio), US West (Oregon), Europe (Frankfurt) and Europe (Ireland). It scores agent traces with LLM-as-judge, offers 13 built-in evaluators, supports ground truth (reference answers and expected tool sequences), and allows custom evaluators as prompts or as Lambda code. Results appear in the AgentCore Observability dashboard in CloudWatch. It works with Strands and LangGraph through OpenTelemetry.

| What we measure | How | Where it shows |
| --- | --- | --- |
| Recall@5 and precision@5 against expected sources | Custom code evaluator (Lambda) compares retrieved doc\_ids with the test set | AgentCore Observability dashboard; askwri-quality dashboard |
| Citation precision (cited passage supports the claim) | Custom LLM-judge evaluator with our rubric | Same |
| Unsupported claims | Count from the verify step, logged per request | Same |
| Decline accuracy | Ground truth marks unanswerable questions; code evaluator checks the decline | Same |
| Helpfulness, faithfulness, tool use | Built-in evaluators | AgentCore Observability dashboard |
| Latency, rounds, tokens, cost per query | Traces + custom metrics, per mode | askwri-quality dashboard |
| Live quality on real demo traffic | Online evaluation sampling live traces | AgentCore Observability dashboard |

**AWS resources and placement**

| Resource | Name | Placement | Access | Check |
| --- | --- | --- | --- | --- |
| Evaluation configuration (on-demand + online) | askwri-eval-config | Regional, managed; must be a region where Evaluations is available | askwri-eval-role reads traces, invokes evaluator Lambdas | An on-demand run over the 20 questions produces scores |
| Custom code evaluator | askwri-eval-citations (Lambda, Python) | Outside the VPC; reads the test set from S3 | askwri-eval-role: s3:GetObject on askwri-corpus eval/\*; logs | Returns recall, precision and decline scores for one trace |
| Custom LLM-judge evaluator | askwri-eval-faithfulness | Regional, managed | Uses a small Bedrock model | Scores a known-bad answer low |
| Test set and results | askwri-corpus eval/ prefix (testset.jsonl, results/) | S3, private | Eval role only | Results file written after each run |
| Custom metrics | Namespace AskWRI/Quality, dimension Mode = quick or deep | CloudWatch, same region | Agent and evaluator roles: cloudwatch:PutMetricData | Metrics appear within minutes |
| Dashboard | askwri-quality | CloudWatch, same region | Team read access | Shows recall, citation precision, unsupported claims, decline accuracy, latency and cost per query for both modes |
| Alarm (optional) | askwri-unsupported-claims | CloudWatch | Notifies the team | Fires if any unsupported claim reaches output |

**Fallback if Evaluations is not enabled in the sandbox region:** run the same Python evaluation script (RAGAS plus our recall script) locally or in a Lambda, write results to askwri-corpus eval/results/, and push the numbers to the AskWRI/Quality namespace so the askwri-quality dashboard still works.

**In the demo:** show the askwri-quality dashboard next to the ablation table, so the accuracy claims are visible in AWS.

## Cost strategy for a nonprofit

The design keeps expensive steps rare and the common path cheap, with no service billing by the hour while idle.

| Cost driver | Risk | How we control it |
| --- | --- | --- |
| Always-on infrastructure | Highest: bills whether used or not | Serverless only: AgentCore, Lambda, Aurora Serverless v2 scaling down; no OpenSearch Serverless |
| Ingestion parsing | Largest one-time cost | Vision model only on flagged table and figure pages; Bedrock batch inference |
| Briefings | Most model calls per request (about 5-8) | Sub-research on a small model; larger model only for final synthesis |
| Q&A | Bulk of traffic, about 2-4 calls | Small model for routing and evaluation; prompt caching on system prompt and tool definitions |
| Retrieval loop | Can multiply calls | Capped at 3 rounds; most queries finish in 1 |
| Verification | Runs on every request | Deterministic citation check first, then Guardrails; deliberate cost for the 100% citation requirement |
| Translation | Repeat requests | Cached; translate output only, never the corpus |

We report measured cost per query from traces, not estimates. That gives WRI a real cost model for scaling to the full 1,348-document corpus.

## Security basics

We meet all three of WRI's security basics and add guardrails against misuse of the agent.

- **Least-privilege IAM:** one role per component (ingestion, agent runtime, API), each scoped to only the S3 prefixes, Aurora database and Bedrock models it needs.
- **No secrets in code:** database credentials in AWS Secrets Manager (or Aurora IAM authentication); Terraform variables, never committed values.
- **Private, encrypted S3:** block public access on, SSE encryption, access only through IAM roles; the UI links to public wri.org URLs, not to our bucket.
- **Agent safety:** document text is treated as data, never as instructions; tools are read-only; Guardrails filters inputs and outputs.
- **Repo hygiene:** scan the repo for credentials before pushing. Remove the password-like string that currently sits under "MVP Definition of Done" in the vision document.

**Network isolation:** Aurora sits in private DB subnets reachable only from askwri-sg-lambda; there is no internet route and no NAT gateway; AWS services are reached through VPC endpoints (see AWS deployment layout).

## Two-day build plan and team split

Day 1 ends with every Must Have working end to end; Day 2 adds differentiators, evaluation and the demo.

| Workstream | Day 1 | Day 2 | Owner |
| --- | --- | --- | --- |
| Infrastructure | Terraform: S3, Aurora with pgvector, IAM roles, AgentCore setup; confirm model access and regions | Deployment polish, README for reproducibility | TBD |
| Ingestion | Sample list, PDF extraction, metadata tagging, chunking, embeddings into Aurora | Figure and table pages via batch; add any missing office papers | TBD |
| Agent and retrieval | Hybrid search + rerank, agent loop with cap, claim-level citations, verification, decline path, evidence labels, authors | Briefing templates, translate tool, coverage tool, outdated-figure flags; multi-agent upgrade if time | TBD |
| UI | Chat, citation cards, reasoning trace | Briefing view, language selector, gap view | TBD |
| Evaluation | Write and verify the 20-question test set; tune the decline threshold | Run the ablation, fill the results table, cost per query | TBD |

**Checkpoints**

1. Day 1 midday: retrieval returns correct passages for the 8 factual test questions.
2. Day 1 end: cited Q&A, decline and briefing work in the UI.
3. Day 2 midday: decide whether to build multi-agent, based on whether Must Haves are solid.
4. Day 2 afternoon: evaluation run complete, demo rehearsed twice.

## Demo script (about 7 minutes)

The demo follows WRI's three user journeys, then closes on the evaluation table.

1. **Cited question (Journey 1).** Ask what WRI has published on electric buses in Latin America. Show sentence-level citations with type and year, open one at the right PDF page, and show the authors panel.
2. **Old-document recovery.** Ask a question only a pre-2010 report answers. Show the reasoning trace where round 2 added older terminology and found it.
3. **Outdated figure.** Ask the pre-chosen question with a revised WRI estimate. Show the flag recommending the newer figure.
4. **Helpful decline.** Ask the unanswerable question. Show what was searched and the nearest related WRI work.
5. **Briefing (Journey 2).** Request a briefing for a partner meeting as talking points, then switch to the policymaker issue-brief format. Ask for it in Spanish; show the machine-translated label and original passages.
6. **Cross-office discovery.** Ask in English and surface a WRI Brasil paper.
7. **Gaps and change over time (Journey 3).** Ask where WRI's work on a topic is thin; show computed coverage and the corpus caveat.
8. **Results.** Show the ablation table: recall, citation precision, decline accuracy, latency and cost per query for each configuration.

## Risks, mitigations and open questions

The largest risks are corpus readiness and PDF parsing; both are addressed before or on the morning of Day 1.

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Corpus not ready or wrong mix | Medium | High | Agree the sample list before the event; download script as fallback |
| Poor PDF parsing | High | Medium | Start with text-heavy documents; vision model only for flagged pages |
| Weakly grounded answers | Medium | High | Claim-level citations, verification, decline path tested on Day 1 |
| Retrieval loop raises cost or latency | Medium | Medium | Cap at 3 rounds; log rounds per query |
| Model not available in sandbox region | Medium | Medium | Confirm on Day 1 morning; cross-region inference |
| No revised-figure pair in sample | Medium | Medium | Find a real case before the event; otherwise drop feature 9 from the demo |
| Mistranslation | Medium | Medium | Label translations, show original, number-preservation check |
| Multi-agent takes too long | Medium | Low | Optional; decided at Day 2 midday checkpoint |

**Open questions for WRI**

- [ ] What format will the document dump use (PDFs, text, metadata file)?
- [ ] Does the dump include pre-2019 publications, and non-English office publications?
- [ ] Can WRI share 15-25 test questions with expected sources? If not, we build our own as described.
- [ ] Should the sample focus on one program or a mix? (We propose 2-3 programs.)
- [ ] Which Bedrock models, AgentCore features and batch inference are enabled in the sandbox region?
- [ ] Can the sandbox role create a VPC, subnets, VPC endpoints and Aurora, or is there a pre-built VPC to use?
- [ ] Is there a known case where a newer WRI publication revised an older estimate?

## Checklist: things to check and do

These are the concrete checks that keep the Must Haves safe; tick them off as a team.

**Before the event**

- [ ] Open the WRI dump link; confirm format, metadata file, pre-2019 documents and non-English office papers.
- [ ] Pick the 100-150 document sample: older documents weighted, 2-3 programs, all 7 publication types, 5-10 office papers.
- [ ] Find one real revised-estimate pair (older and newer WRI figure on the same metric) and confirm both are in the sample.
- [ ] Record wri.org URLs for every sampled document (doc\_id); note DOIs only where they exist.
- [ ] Draft the 20-question test set with expected document and page; include 2 old-document, 2 cross-language, 1-2 revised-figure and 2-3 unanswerable questions.
- [ ] Prepare the Terraform skeleton: VPC, subnets, security groups, endpoints, Aurora, S3, IAM roles, default\_tags.
- [ ] Decide the agent framework (Strands or LlamaIndex Workflows) based on team familiarity.
- [ ] Remove the password-like string under "MVP Definition of Done" in the vision document.

**Day 1 morning (first 2 hours)**

- [ ] Confirm sandbox region; test Bedrock access to the embedding, rerank, small and large models; enable cross-region inference where needed.
- [ ] Confirm AgentCore Runtime, Gateway, Memory and Bedrock batch inference are available in the region.
- [ ] Confirm the sandbox role can create a VPC, subnets, VPC endpoints and Aurora; otherwise ask for a pre-built VPC and adapt subnet names.
- [ ] `terraform apply`; check every resource appears in the askwri-rg resource group with the Project = AskWRI tag.
- [ ] Run `CREATE EXTENSION vector;` on askwri-db; confirm "Publicly accessible: No".
- [ ] Check S3 Block Public Access is on for both buckets; anonymous object URLs return 403.
- [ ] From a tool Lambda, reach Aurora, Secrets Manager and Bedrock through the VPC endpoints (no NAT).
- [ ] Upload the sample PDFs to askwri-corpus raw/ from a laptop or CloudShell; confirm the ingestion Lambda produces chunks with page numbers.

* [ ] Confirm AgentCore Evaluations is available in the sandbox region; if not, use the evaluation fallback in Quality dashboard in AWS.
* [ ] Create the askwri-quality CloudWatch dashboard and the AskWRI/Quality metric namespace.
* [ ] Install `@worldresources/wri-design-systems` in the Next.js app and confirm it builds.
* [ ] Test a presigned download link for one PDF from askwri-corpus raw/.

- [ ] Ingest the largest sample PDF first and time it; it must finish well under the 15-minute Lambda limit. Confirm the ingestion function's reserved concurrency is 10.

**Day 1 end**

- [ ] 8 factual test questions return the expected passages in the top 5.
- [ ] Every answer sentence carries a citation that opens the right PDF page.
- [ ] Unanswerable questions are declined with nearest related work; decline threshold tuned.
- [ ] Briefing works end to end in the UI.

**Before the demo**

- [ ] Ablation table filled from real runs, with cost per query from traces.
- [ ] Demo script rehearsed twice; fallback screenshots ready.
- [ ] MCP Inspector or Claude Desktop connected to askwri-gateway with a Cognito token for the MCP tool demo.
- [ ] Repo README lets someone reproduce the deployment with Terraform.

**After the event**

- [ ] `terraform destroy` to remove VPC endpoints, Aurora and everything else that bills; confirm askwri-rg is empty.

## To do: voice input

Voice lets people ask by speaking; we start with speech-to-text into the existing agent, and treat full spoken conversation with Amazon Nova Sonic as a stretch.

**Bedrock and AWS options**

| Option | What it is | Fit for AskWRI | Notes to check |
| --- | --- | --- | --- |
| A. Amazon Transcribe streaming (speech to text) + existing agent | Converts the question to text, then the normal Quick answer or Deep research runs | **Recommended first step**: reuses the whole pipeline; citations stay on screen | Supported languages for WRI offices (English, Spanish, Portuguese, Indonesian); streaming from the browser |
| B. A + Amazon Polly (text to speech) | Reads the short answer aloud | Easy add-on for Quick answer | Read the summary only; sources stay on screen |
| C. Amazon Nova Sonic on Bedrock (speech to speech) | One model that listens and speaks in real time over a bidirectional streaming API, with tool calling | Stretch: a spoken research assistant that calls our search tools | Nova 2.5 Sonic went GA on Bedrock on October 5, 2026, in US East, US West, Stockholm and Tokyo; seven languages; asynchronous tool calls. Uses a bidirectional streaming API, not the Converse API |

**Design rules for voice**

- Spoken answers are short and end with "sources are on your screen"; citations are never read out in full.
- Show the transcript of the question so users can correct it before searching.
- Deep research stays text-first; voice can start it, and the report appears in the side panel.

**AWS resources and placement**

| Resource | Name | Placement | Access | Check |
| --- | --- | --- | --- | --- |
| Transcribe streaming | Called from askwri-api via a WebSocket or presigned streaming URL | Regional, managed; outside the VPC | askwri-api-role: transcribe:StartStreamTranscription | Spoken question returns correct text in each target language |
| Polly (option B) | Called by askwri-api | Regional, managed | askwri-api-role: polly:SynthesizeSpeech | Answer summary plays in the browser |
| Nova Sonic session (option C) | askwri-voice service on AgentCore Runtime if it supports bidirectional streaming in our region, otherwise an ECS Fargate service | Same region as Nova Sonic availability; outside the VPC; calls askwri-gateway tools | askwri-voice-role: bedrock:InvokeModelWithBidirectionalStream on the Sonic model; Gateway invoke | A spoken question triggers the search tool and returns a spoken summary |

**To do**

- [ ] Confirm the sandbox region supports Transcribe streaming for English, Spanish, Portuguese and Indonesian.
- [ ] Add a microphone button to the search box; show the live transcript.
- [ ] Route the final transcript into the normal Quick answer or Deep research call.
- [ ] Optional: Polly read-aloud for Quick answer summaries.
- [ ] Stretch: check Nova Sonic availability in the sandbox region (or cross-region access), then prototype a Sonic session that calls the search tool.
- [ ] Add 2-3 spoken questions to the test set and measure transcript accuracy and answer recall.

## Backlog

These are deferred so the Must Haves and chosen differentiators get the time; pick them up only if Day 2 has room.

| Item | Why deferred | Effort |
| --- | --- | --- |
| "Run Deep research" suggestion button when Quick answer evidence is weak or the question is broad | Nice cost-control touch, not needed to show either mode | Low |
| Expected time and depth text on the Deep research toggle | Polish; live progress already sets expectations | Very low |
| Full spoken conversation with Nova Sonic (voice option C) | Depends on region availability and a streaming service | Medium-High |
| Multi-agent workers in Deep research | Optional in WRI's scope; decided at the Day 2 midday checkpoint | Medium |

## Implementation runbook

Build in seven phases, each ending with its checks passing, using Terraform for every AWS resource so the sandbox is reproducible and can be destroyed in one command.

**Credentials (read first)**

- Never paste long-lived AWS access keys into a chat, a doc or the repo.
- Use temporary credentials: IAM Identity Center (`aws sso login --profile askwri`) or the sandbox's temporary keys loaded into a local AWS CLI profile, then run Terraform and any coding assistant from that terminal with `AWS_PROFILE=askwri`.
- Alternative: run Terraform from AWS CloudShell inside the sandbox account, where credentials are already present.

**Prerequisites:** Terraform 1.6 or later, AWS CLI v2, Python 3.12 with uv, Node 22.14 and Docker. In the Bedrock console, enable access to the embedding, rerank, small, large and vision models.

**Repository layout**

```
askwri/
  infra/              Terraform root + modules: network, storage, database, ingest,
                      tools, gateway, agent, api, ui, observability, voice (optional)
  db/schema.sql       Tables and indexes
  ingest/             Lambda: extract by page, dates, tagging, chunk, embed, write
  tools/              Lambdas: search, passage, coverage, authors, translate
  agent/              Agent loop (Strands or LlamaIndex Workflows), prompts, Dockerfile
  api/                FastAPI: chat, sources download, transcribe (optional)
  web/                Next.js + @worldresources/wri-design-systems
  eval/               testset.jsonl, run_eval.py, evaluator Lambdas
  README.md           Deploy, test and destroy steps
```

**Configuration values (infra/terraform.tfvars)**

| Variable | Value |
| --- | --- |
| region | Sandbox default region (confirm Bedrock, AgentCore and Evaluations availability) |
| project | askwri |
| tags | Project = AskWRI, Environment = hackathon, Team, Owner, ManagedBy = terraform |
| vpc\_cidr | 10.20.0.0/16 |
| embedding\_model\_id, embedding\_dim | Multilingual Bedrock embedding model and its vector size |
| rerank\_model\_id | Bedrock rerank model |
| small\_model\_id, large\_model\_id | Haiku-class and Sonnet-class models (or cross-region inference profiles) |
| vision\_model\_id | Vision-capable model that supports batch inference |
| quick\_max\_rounds, deep\_max\_rounds | 2 and 3 |

**Database schema (db/schema.sql), outline**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
  doc_id text PRIMARY KEY, url text, doi text, file_sha256 text UNIQUE,
  title text, year int, pub_date date, date_source text, date_confidence text,
  pub_type text, office text, program text, countries text[], regions text[],
  topics text[], authors text[], language text
);

CREATE TABLE chunks (
  chunk_id text PRIMARY KEY, doc_id text REFERENCES documents(doc_id),
  page int, content text, is_table_or_figure boolean DEFAULT false,
  embedding vector(1024),  -- set to embedding_dim
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
);

CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON chunks USING gin (tsv);
CREATE INDEX ON documents (year, pub_type, program, language);

CREATE TABLE translations (hash text PRIMARY KEY, lang text, text text);
```

The 'simple' text-search configuration keeps keyword search language-neutral across English, Spanish, Portuguese and Indonesian.

**Build phases**

| Phase | Build | Terraform modules / code | Done when |
| --- | --- | --- | --- |
| 1. Foundation | VPC, 4 private subnets, security groups, VPC endpoints, S3 buckets, Aurora, secrets, resource group | network, storage, database | All checks in AWS deployment layout pass; `db/schema.sql` applied |
| 2. Ingestion | Ingestion Lambda with S3 trigger, date rules, tagging, embeddings; vision batch job | ingest; ingest/ | Sample uploaded to raw/; documents and chunks tables populated with page numbers and date\_source |
| 3. Tools and gateway | Five tool Lambdas, askwri-gateway-role, Cognito askwri-auth, AgentCore Gateway | tools, gateway; tools/ | MCP Inspector with a token lists 5 tools and search returns cited passages |
| 4. Agent | ECR repo, agent image, AgentCore Runtime, Memory, Guardrail; Quick answer and Deep research modes | agent; agent/ | Test invocations return cited answers in both modes and decline unanswerable questions |
| 5. API and UI | FastAPI Lambda, HTTP API, sources download route, Next.js on S3 + CloudFront | api, ui; api/, web/ | End-to-end chat in the browser with citation cards, downloads and the Deep research toggle |
| 6. Evaluation | Test set in S3, evaluator Lambdas, Evaluations config, CloudWatch dashboard and metrics | observability; eval/ | askwri-quality dashboard shows both modes; ablation table filled |
| 7. Voice (optional) | Transcribe streaming route, optional Polly | voice; api/ | Spoken question returns a cited answer |

**Commands**

```bash
# 1. Authenticate with temporary credentials
aws sso login --profile askwri && export AWS_PROFILE=askwri

# 2. Deploy infrastructure
cd infra && terraform init && terraform plan -out plan.tfplan && terraform apply plan.tfplan

# 3. Apply the schema (from a tool Lambda, the RDS Query Editor, or CloudShell in the VPC)

# 4. Upload the corpus
aws s3 sync ./corpus s3://askwri-corpus-<account-id>/raw/

# 5. Build and push the agent image, then re-apply to point the runtime at it

# 6. Run the evaluation
uv run python eval/run_eval.py --mode quick && uv run python eval/run_eval.py --mode deep

# 7. Tear down after the event
cd infra && terraform destroy
```

## Sources

- AskWRI Vision Document and AskWRI Technical Environment Document (provided by WRI)
- [Excellence in Research – WRI](https://www.wri.org/research/excellence)
- [Opportunities to Build Data Tools That Deliver – WRI Data Lab](https://www.wri.org/update/opportunities-build-data-tools-deliver)
- [Data Lab 2025 series overview – WRI](https://www.wri.org/update/data-lab-series-2025-technology-for-people-nature-climate)
- [Example WRI DOI record – Policy Commons](https://policycommons.net/artifacts/1422655/public-international-funding-of-nature-based-solutions-for-adaptation/2036752/)
- [WRI Publications and World Resources Report history](https://tools.wri.org/publication)

* [AgentCore Evaluations is now generally available – AWS](https://aws.amazon.com/about-aws/whats-new/2026/03/agentcore-evaluations-generally-available)
* [Evaluate agent performance with AgentCore Evaluations – AWS docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html)
* [Introducing Amazon Nova 2 Sonic – AWS News Blog](https://aws.amazon.com/blogs/aws/introducing-amazon-nova-2-sonic-next-generation-speech-to-speech-model-for-conversational-ai)
* [Amazon Nova 2.5 Sonic on Bedrock – AI Weekly](https://aiweekly.co/alerts/amazons-nova-25-sonic-voice-model-hits-bedrock-in-four-regions)
* [wri/wri-design-systems – GitHub](https://github.com/wri/wri-design-systems)
* [How WRI Product Studio is Using AI to Build Faster – WRI](https://www.wri.org/update/how-wri-product-studio-using-ai-build-faster)
