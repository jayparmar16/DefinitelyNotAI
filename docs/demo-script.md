# AskWRI live demo script

Six examples, about 10 minutes, each showing different features. Every question here was run on
the live system the night before; the times are from that run, warm. The first question after
a quiet spell takes about twice as long while the agent starts.

## Before you start

1. Open https://d17gz0gh5g00t3.cloudfront.net in an Incognito window (extensions blocked the
   admin page in a normal one) and sign in.
2. Two minutes before: ask any question once, so the agent is warm.
3. Start each example with **New chat** (top left) after the previous answer has finished;
   pressing it while an answer is still streaming stops that answer.
4. Keep the side panel open (it opens when you click a source or Visuals).

## 1. A cited answer you can check (about 20 s)

Ask: **How should civil society track adaptation finance?**

Show:
- The summary at the top, then the answer: every sentence carries [n] markers.
- "Verified 8 of 8 claims": each claim was checked against its passage, then by Bedrock
  Guardrails grounding; anything unsupported is removed, never shown.
- Click a marker: the source opens at the cited page of the real PDF, the passage highlighted.
- **Visuals** → Evidence matrix: which publication backs which point ("Tracking steps",
  "Challenges", "Philippines example"). Click **Expand**.

Say: every claim is traceable to a page of a WRI publication.

## 2. Written for the reader, without picking a persona (about 20 s, then 25 s)

Ask: **Give me points I can use with a funder on why invest in restoring degraded land**

Show: "Written for: Partnerships", inferred from the question ($7–30 returned per dollar
invested; degradation costs more than US$6.3 trillion).

Then turn on **Deep research**, report type **Issue brief**, ask:
**Methane mitigation in agriculture**

Show: a policymaker issue brief (problem, evidence, options), 7 of 7 claims verified, 11 sources.
Switch the report type to **Talking points**: it redrafts from the same sources, no new search.

## 3. Topic spaces and WRI's own metadata (about 25 s)

In the left sidebar, click the **Ocean** space (21 publications). Ask:
**What did WRI publish in 2025 on ocean?**

Show: "Searching the Ocean space only"; every source is a 2025 Ocean publication (the year
comes from wri.org, the document, or its folder: 573 of 579 documents now have one). Open a
source: its topics and WRI's own abstract are in the side panel.

Say: researchers work inside a topic; nothing outside it leaks in. "Search all of WRI" is one
click away.

## 4. It won't make things up (about 20 s each)

Ask: **Why did WRI conclude that electric vehicles increase urban air pollution?**

Show: it declines, because WRI never concluded that, and it shows what it searched and the
closest real WRI work.

Then switch the tool to **Fact-check** and paste:
**WRI found that 281 of 394 European cities did not meet the 2030 air quality standards, and
that transport is the main source of pollution.**

Show: the first claim is marked contradicted (WRI's figure is different) with the passage; the
second is marked not found.

## 5. Ask in your language (about 25 s)

Ask: **¿Qué recomienda WRI para reducir el calor extremo en las ciudades?**

Show: the answer is in Spanish, 8 of 8 claims verified, and the sources keep their original
English titles and passages, so the citation is still exact. Every number was checked to
survive translation.

## 6. Explore a topic: timeline, citation graph, key figures (about 20 s)

Switch the tool to **Explore** and type: **adaptation finance**

Show:
- Key figures, quoted word for word from the passages.
- Citation map: 13 publications from 2014 to 2026, as a family tree; 7 of 12 link to each other.
  Click **Expand**, then tick **Reports beyond the answer** to see what else cites them.
- Click a report: what it builds on and what builds on it, with the citing sentence; **Open
  page** jumps to it. **Download links (CSV)** for a literature review.

Say: it shows how WRI's research connects, not just what one report says.

## If there is time

- **Topic dossier** (Deep research, report type Topic dossier): **Adaptation finance
  accountability**: 8 papers through a fixed lens, where they agree and differ, and what's
  missing. About 55 s.
- **Charts are searchable**: **Which sectors account for the largest share of global methane
  emissions, according to WRI charts?** (16 s). The answer draws on a chart's description
  (1,344 images and 945 charts were described during ingestion).
- **Admin page** (`/admin/`, admins only): the evaluation scorecard against WRI's targets, cost
  per answer, and the most expensive questions.

## What makes it different (one line each)

- Every claim is verified twice (claim check and Bedrock Guardrails grounding); unsupported
  sentences never reach the reader.
- It declines instead of guessing, and shows what it searched.
- Sources open at the exact page with the passage highlighted.
- Research tools, not just chat: Deep research reports, fact-check, research lens, topic
  dossier, citation graph.
- Built on WRI's own metadata: topics, years, abstracts, initiatives, figure descriptions.
- On AWS: AgentCore Runtime, Gateway (MCP tools), Memory and Evaluations; Aurora pgvector with
  Cohere Embed v4; Bedrock Guardrails; Cognito sign-in; CloudFront.
