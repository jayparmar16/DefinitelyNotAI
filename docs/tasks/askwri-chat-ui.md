# AskWRI chat UI

Owner: AlekyaKowta
Status: in-progress
Design: AskWRI design system (claude.ai artifact, owner's account): tokens, components, four
screens. Spec: docs/askwri-solution-design.md ("UI design", "Two modes", "Citations, sources
and downloads").

## Goal

The chatbot interface from the AskWRI design system, running against a mock agent until the
backend API exists, so the UI and the backend can be built in parallel and joined at one seam.

## Done when

- [x] Welcome screen with suggested questions for WRI's three user journeys; clicking one fills
      the composer and never sends.
- [x] Quick answer: every sentence's `[n]` marker links to its source card; clicking a marker
      outlines the card and opens the source at the cited page in the side panel.
- [x] Citation cards: title, type tag, year · office · page, quoted passage (or "cited by page"
      when not quotable), Open at page (wri.org `#page=N`), PDF, Cite.
- [x] Deep research: live progress trace with Stop, sources streaming in, outdated-figure flag,
      report in the side panel with format and audience, people behind the work.
- [x] Helpful decline: what was searched, the closest related work, Rephrase.
- [x] An answer whose marker has no source is never shown.
- [x] Downloads: answer or report as Markdown, sources as CSV or BibTeX, copy as Markdown.
- [x] Translation is labelled "Machine-translated", with the original one click away.
- [x] Works at phone width; side panel is resizable and closable.
- [ ] Real agent client replaces the mock (needs the API, runbook phase 5).
- [ ] PDF viewer renders the stored PDF with PDF.js over the presigned URL (needs the API).
- [ ] Hosting: askwri-ui bucket + askwri-cdn CloudFront (runbook phase 5).

## Decisions

- The mock lives only in `web/src/mock/`; the UI reaches it only through `getAgent()` in
  `web/src/lib/agent.ts`, so removing it is one folder plus one function.
- Styles are ported from the AskWRI design system (its values are WRI Design System tokens),
  not WRI's React components: those need a Chakra and Emotion provider setup, and the design's
  AskWRI pieces (markers, cards, trace, panels) are custom anyway. WRI's components can still
  be swapped in later.
- Tests use Node's built-in test runner: no test dependency.
- Voice (mic button) and "Try Deep research" on the decline are hidden: a to-do and a backlog
  item in the design doc.
- Static export (`output: "export"`), matching S3 + CloudFront hosting.
- `agentRules: false` in next.config: Next 16 otherwise writes a web/AGENTS.md, and the root
  AGENTS.md is the repo's single source of instructions.

## Handoff

None yet.
