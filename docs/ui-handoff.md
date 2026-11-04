# AskWRI UI handoff: every feature the new UI must keep

This is for whoever redesigns the AskWRI chat UI (`web/`). Change the look freely; keep every
behaviour below, and keep the checks at the end green. The agent and API are deployed and
don't change for a redesign: the UI talks to them only through `web/src/lib/agent.ts`.

Branch: `askwri-chat-ui`. Read `AGENTS.md` first (repo rules: no AI attribution in commits,
no secrets in code).

## 1. Run it

```bash
cd web
npm install
npm run dev          # http://localhost:3000
npm test             # unit tests (Node's built-in runner)
npm run lint         # type check
npm run build        # static export to web/out
```

- **Mock mode (no AWS needed):** with no `NEXT_PUBLIC_ASKWRI_API_URL` set, the UI uses the mock
  agent in `src/mock/` and shows a "Mock data" badge. Every feature below has a mock
  (fact-check cycles through all verdicts; the lens alternates summarised and "not discussed"
  cells). Design against the mock first.
- **Real agent:** create `web/.env.local` (gitignored) with `NEXT_PUBLIC_ASKWRI_API_URL` and
  `NEXT_PUBLIC_ASKWRI_API_KEY`; ask Alekya for the values. The API only accepts browser calls
  from `http://localhost:3000`: use that port, or ask for your origin to be added
  (Terraform `allowed_origins`, which also covers the PDF downloads).

## 2. How the UI talks to the agent

Everything goes through the `AgentClient` in `src/lib/agent.ts` (types are the contract; read
that file). `getAgent()` returns the HTTP client (`src/lib/httpAgent.ts`) or the mock.

| Call | API | Notes |
|---|---|---|
| `ask(request, signal)` | `POST /chat` | Server-sent events (`src/lib/sse.ts`). The Stop button aborts `signal`. |
| `warmup(sessionId)` | `POST /warm` | Starts the chat's agent at the first keystroke (cold start 6-9 s). **The first question must wait for an in-flight warm-up** (see `warming` in `ChatApp.tsx`), or the runtime rejects it. |
| `sourceDownloadUrl(source)` | `GET /sources/download?key=raw/…pdf` | 5-minute presigned link to the stored PDF, served inline as `application/pdf`. |
| `translate(paragraphs, language, sessionId)` | `POST /chat` with "Now in Spanish" | Follow-up on the same session; returns every translated section. |

Every request carries `X-AskWRI-Key`. `AskRequest` fields: `question`, `mode`
(`quick` / `deep` / `factcheck`), `language`, `audience` (`auto` by default), `format`,
`filters`, `sessionId`, `deep` (fact-check only), `lens`.

**Stream events** (one run ends with exactly one `answer`, `decline` or `factcheck`):

| Event | Use |
|---|---|
| `step` (id, label, detail?, status now/done) | Live progress; a repeated id updates that step. Step id `context` = how a follow-up was read (show it under the question, see 4.3). |
| `source-found` | "Found so far" while Deep research runs. |
| `outdated-figure` | A flag above the answer. |
| `answer` | The answer (section 4.1). |
| `decline` | No strong evidence: message, what was searched, closest WRI work. |
| `factcheck` | A checked draft (section 4.6). |

Before showing an answer the UI checks every `[n]` marker has a source
(`unmatchedMarkers`); an answer citing a missing source is never shown. Keep that check.

## 3. Layout today (change freely)

Header (logo, Audience, Language, Download, New chat) · left **chats sidebar** · conversation
column · **composer** at the bottom · resizable right **side panel** (report, sources, open
PDFs as tabs). Phone width: sidebar and side panel slide over the chat. Tokens and component
styles are in `src/app/globals.css` (from the AskWRI design system artifact).

## 4. Features and the behaviour each must keep

### 4.1 Cited answers (Quick answer)
- Text with `[n]` markers; clicking one opens that source in the side panel and highlights its
  row in the sources list.
- Header chips: mode, **"N of M claims verified"** (expands to the claims verification
  removed, `removedClaims`), **"Written for: <reader>"**, source count, seconds.
- **Scope line** under it: "Based on N of the M WRI publications indexed in AskWRI".
- **Possible implications** must stay visibly labelled *AskWRI's interpretation, not WRI
  findings* (they carry no citations).
- **What this can't tell you** (`limits`), and **Questions to explore** (`questions`): clicking
  one fills the composer (does not send).
- Actions: Copy, Download (Markdown), Translate, Turn into briefing (asks Deep research).

### 4.2 Reader tailoring ("Written for")
- Audience defaults to **Auto**: the agent infers researcher / policymaker / partnerships from
  the question; nobody has to pick a persona.
- The "Written for" chip lets the user re-ask the same question for another reader.
- The header Audience selector forces a reader for all questions.

### 4.3 Chats, sessions and follow-ups
- Each chat has a `sessionId` (random UUID); **New chat** makes a new one. The agent keeps the
  conversation in AgentCore Memory for 7 days, keyed by that ID.
- Follow-ups are read in context by the agent: "what about Kigali?" is rewritten into a full
  question (step id `context`, shown as **"↳ Read in context as: …"** under the question);
  "make it shorter / talking points for a funder" reuses the previous sources with no new
  search; "now in Spanish" translates the previous answer.
- **The open chat and the 10 most recent are kept in this browser** (`src/lib/chats.ts`,
  localStorage, all access in try/catch). Refresh keeps the chat; the sidebar reopens older
  chats (grouped Today / Earlier) and continues their session.

### 4.4 Sources and the PDF side panel
- Under each answer: a **collapsed** "Sources · N passages from M publications" line with
  marker chips; expands to slim rows (title, type · year · office · page); a row expands to
  its quoted passage and View page / wri.org / PDF / Cite. CSV and BibTeX export.
- Publication type labels come from the data (Report, Working paper, Technical note, …);
  working papers show "(in progress)".
- **Side panel source view** (`PdfPage.tsx`): draws the cited PDF page with PDF.js, finds the
  cited passage in the page's text layer and wraps it in `<mark class="cite-highlight">`
  (yellow), scrolls to it, and says "Cited text highlighted on page N of M" (or that the exact
  wording couldn't be matched). Above it: the cited passage and **"Found by meaning /
  keywords (terms)"**, plus whether the publication type moved it up or down. Prev / next
  citation, Open full PDF. Matching logic and tests: `src/lib/highlight.ts`.
- Non-quotable passages (re-ordered in the PDF) are cited by page and never quoted.

### 4.5 Deep research reports
- Toggle in the composer. Opens the side panel's Report tab: title, "Built from N WRI
  publications, years", key points with markers, "Where the evidence is thin", people behind
  the work, format switch (talking points / issue brief / researcher summary), Markdown.

### 4.6 Fact-check my draft
- Composer switch **Ask | Fact-check**; in Fact-check the Deep toggle means "more passages per
  claim, and a second search for unsettled claims".
- Result (`FactCheckCard.tsx`): the user's draft with each claim highlighted by verdict
  (**supported** green, **contradicted** red, **outdated** amber, **not found** grey);
  clicking a claim jumps to its row. Each row: verdict, the claim, [n] sources, **Suggested
  wording** (WRI's figures) for contradicted/outdated, and a note. Summary line, Copy report.
- Helpers and tests: `src/lib/factcheck.ts`.

### 4.7 Research lens
- **Lens** button in the composer: a goal and up to 4 aspects (chips). An active lens shows as
  a bar above the input (Edit, ✕) and is sent with every Ask question in the chat.
- Answers then show **"Through your lens"**: one row per paper, one column per aspect, each
  cell a cited summary, *"Not discussed in this paper"*, or *"No verified summary"*. The side
  panel shows that paper's lens summary above the cited passage.

### 4.8 Languages
- Language selector (English, Español, Português, Bahasa Indonesia). With English selected, a
  question asked in Spanish is answered in Spanish. Translated answers are labelled
  **Machine-translated**; sources keep their original titles and passages. Translate menu and
  "Show original" on each answer.

### 4.9 Declines and errors
- A decline shows the message, what was searched (chips), closest related WRI work, Rephrase
  and Copy what was searched. A failed run shows the API's message.

### 4.10 Downloads
- Answer/report as Markdown (includes scope, implications, limits, questions), sources as
  CSV/BibTeX, copy as Markdown. Fact-check report as Markdown.

## 5. Coming next (design room for them)
- **Topic dossier**: a fourth Deep research format with one card per document, where documents
  agree / differ / what's missing, and an evidence matrix (documents × fields) with CSV export.
  The answer will carry a `dossier` field (added to `agent.ts` when built).
- **Citation graph / research lineage** once older documents are loaded: "Cited by N in this
  collection" in the source view and a lineage timeline tab.

## 6. Checks to keep green
- `npm test`, `npm run lint`, `npm run build`.
- At 390 px wide nothing overflows the screen; at 1280 px the side panel and sidebar fit.
- With the mock: ask a question, open a source, Deep research, fact-check, lens, translate,
  refresh (chat stays), new chat, reopen from the sidebar. No console errors.
- With the real API: a [1] marker opens the PDF with the passage highlighted.
- Keep dark-on-light contrast for the verdict colours, and keep the "AskWRI's
  interpretation" label on implications.
