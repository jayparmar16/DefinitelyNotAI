# DefinitelyNotAI

AskWRI: a research assistant that answers questions from World Resources Institute
publications, with a citation for every claim. Built on Amazon Bedrock and AgentCore for an
AWS hackathon.

## Get started

1. Install [Claude Code](https://docs.claude.com/en/docs/claude-code) or [Codex](https://developers.openai.com/codex).
   Either works, and teammates can mix them.
2. Clone the repo and open your AI tool in it:

   ```sh
   git clone https://github.com/jayparmar16/DefinitelyNotAI.git
   cd DefinitelyNotAI
   claude        # or: codex
   ```

3. Type **`/setup`** (Claude Code) or **`$setup`** (Codex) and do what it says until
   every line says PASS.

## Every task

| When you want to | Claude Code | Codex |
|---|---|---|
| Start a task | `/claim-task` | `$claim-task` |
| Stop before it's done | `/handoff` | `$handoff` |
| Check your code | `/review` | `$review` |
| Finish and open a PR | `/create-pr` | `$create-pr` |

You can also just say it in plain words, e.g. "claim a task for PDF ingestion" or "open a PR".

## Ingest PDFs locally

The ingestion pipeline (spec: issue #2) turns WRI PDFs into audited, citable chunks.

```sh
uv sync                                   # install Python dependencies
uv run pytest                             # run the tests
uv run python -m askwri.ingest path/to/report.pdf --out chunks/
```

For each PDF the command writes one `.txt` file per chunk, plus a `.metadata.json` sidecar,
under `chunks/<doc_id>/` (a stand-in until the chunks go to Aurora pgvector, #11). Before
anything is written, the citation audit checks every chunk against the PDF's own text layer:

- **Blocked:** a chunk that is empty, garbled, or has words that aren't on its page. Nothing
  is written for that PDF, and the command exits with an error.
- **Page ranges:** a chunk may run on across a page break when its section continues. It
  records where it starts and ends (`pdf_page`, `pdf_page_end`), and the audit checks that its
  first passage is on the first page and its last on the last.
- **Not quotable:** a chunk whose words are all on its page, but in a different order (for
  example diagram labels). It is written with `quotable: false`, so answers can cite its
  page but never quote it word for word.

Chunks are sized for vector search: 400 to 2,000 characters (about 100 to 500 tokens), set by
`MIN_CHUNK_CHARS` and `MAX_CHUNK_CHARS` in `askwri/ingest/chunks.py`, to be tuned against the
evaluation questions. A chunk never crosses a heading. Short paragraphs merge with their
neighbours in the same section; a paragraph over the maximum is cut at sentence boundaries
(a single sentence is never cut, so one longer than the maximum stays whole). A section
whose whole text is short stays one short chunk. Each chunk has `seq`, its position in the
document's chunk order (1, 2, 3, ... with no gaps, the same on every rerun), so a short hit's
neighbours can be fetched by `seq`.

Each sidecar carries two kinds of page number. `pdf_page` and `pdf_page_end` are numbers (the
position in the file, for opening the PDF at the right page). `printed_page` and
`printed_page_end` are the numbers printed on the pages, as text because front matter uses
Roman numerals ("iv"). They come from the PDF's page labels where it has them, else from the
page-header or page-footer text (a number counts only when at least two pages agree on the
same offset from the PDF page). When neither exists, `printed_page` is the PDF page and
`printed_page_fallback` is `true`. Page headers and footers never appear in chunk text.

Each table becomes its own chunk of kind `table` (see "Table chunks" below).

The command also looks each PDF up on wri.org (it needs internet access). It finds the document's own WRI DOI in its suggested-citation block and resolves
`doi.org/<doi>`; with no DOI, or a DOI whose page has a different title, it matches the PDF
title against the wri.org sitemap. A page is used only if it answers 200 and its title
matches. From that page the WRI type, authors, publication date (`wri_published`), tags and
topic are read. The topic is `wri_topic` mapped onto the 11 topics, else the first tag that
is one of them, else empty (never an error). The topic, year, type, tags and link are copied
onto every chunk record (and its sidecar) next to `label_source`.
`chunks/catalog.json` holds one row per document with its labels, link, DOI and label source.

When the title from the PDF's metadata finds no page (it is often "HIGHLIGHTS" or a file
name), the lookup is retried with the title quoted in the suggested-citation block.

Where wri.org has no labels, the `labeler` model (see Models) fills them in. It reads only the
first pages as text and returns structured output, with the topic limited to the 11 topics or
`none` (any other value fails the document). It never overwrites a label wri.org has.

- **No page:** the model gives the title, date, document type, topic, countries and a short
  summary; an RFP also gets its `deadline` (its country is in `countries`). `label_source` is
  `model`.
- **Page without a usable topic:** the model gives only the topic. `label_source` stays
  `wri.org`, and the catalog's `topic_source` is `model`.

The Bedrock client is created only when a document first needs the model (a missing wri.org
page, or a table to describe), so a run where every document has a wri.org page and no
tables needs no AWS setup. Otherwise it needs Bedrock access to the `labeler`
model and a region (`AWS_DEFAULT_REGION`, see Models). A refused or failed model call fails that document with an error naming it.

### Table chunks

- **What is in one:** the caption, the Markdown rows, and the `Notes:` and `Sources:` lines
  under the table, as the chunk's `text`. The caption is the nearest `Table N` heading or
  caption region on the page, above the table or (if it is much nearer) below it; it does not
  have to be the next region, and it never becomes a section heading. `number` is the table
  number ("Table 2", "Table A-1"); it is empty when the caption has none.
- **Large tables:** a table over 2,000 characters is cut by rows into pieces that each repeat
  the caption and the header row. Notes go on the last piece. A row is never cut.
- **Continued tables:** a table whose number repeats on the same or the next page (for
  example "Table 3 (cont.)") is a continuation. Every later piece, including row pieces,
  has `table_first_chunk`, the `chunk_id` of the first piece; each piece keeps its own page.
- **Not a table:** a grid with no caption and no numbers (a grid of names), a contents list
  with dot leaders, or a table whose cell words the layout model got wrong stays a text
  chunk.
- **Description:** the `labeler` model writes one or two sentences per table chunk, stored in
  the chunk's `description`. It is embedded and searched with the chunk (`indexed_text`) but
  is not in `text`, so it is never quoted. Documents that fail the audit get no model calls;
  a model refusal or error fails the document.
- **Quotable:** the audit checks each row of a table on its own (a text layer often reads a
  table column by column, so no whole table is one run of text).

## Models

Every model call picks its model by role from the registry in `askwri/models.py`, so swapping
a model is a one-line change:

| Role | Model ID |
|---|---|
| `vision`, `answerer` | `global.anthropic.claude-sonnet-5-5` |
| `labeler` | `global.anthropic.claude-haiku-5-5` |
| `embedder` | `amazon.titan-embed-text-v2:0` |
| `reranker` | `amazon.rerank-v1:0` |

Region is **us-west-2**: set `AWS_DEFAULT_REGION=us-west-2` (or `AWS_REGION`). Claude is
called through the Anthropic SDK's `AnthropicBedrock` client on the `bedrock-runtime`
endpoint, signed (SigV4) with credentials from the standard AWS chain: environment
variables, `AWS_PROFILE`, or the task role. (The newer `bedrock-mantle` endpoint and
`AnthropicBedrockMantle` client are not used: AWS lists these two models on Mantle only in
GovCloud.) Calls need Bedrock model access for both Claude models in the account.

```sh
uv run python -m askwri.models smoke   # one tiny call per Claude role: PASS or the exact error
```

The smoke test sends an image to `vision`, asks `labeler` for structured (JSON Schema)
output, and asks `answerer` a plain question. In code, use `call_claude` (text) or
`call_claude_json` (structured). Both take the client as their first argument, so tests pass
`tests/fake_claude.FakeClaude` and never touch the network. A refusal, a truncated reply or
an API error raises `ModelError` naming the document.

## The rules

- `main` is protected, so every change goes in through a pull request.
- Write only the code the task needs. `review` flags anything extra.
- Commits that contain secrets are blocked.
- Your own AI tool settings stay on your machine (git ignores them).

The full rules for people and agents are in [AGENTS.md](AGENTS.md).

## FAQ

**`/setup` shows FAIL lines.**
Each FAIL line prints its fix. Your AI runs the fixes it can. Logins you have to run
yourself (in Claude Code, type the command with a `!` in front, e.g.
`! gh auth refresh --scopes repo,workflow`). Then run `/setup` again.

**Push fails with "Permission denied" or 403.**
You aren't a collaborator yet. Send your GitHub username to the repo owner (jayparmar16).

**Push to `main` fails with "protected branch".**
That's expected: work goes on a branch. Move your commits to a new branch, then reset your
local `main`:
`git switch -c my-task && git branch -f main origin/main`

**How do I see who's working on what?**
Each open draft PR is a task someone has claimed. Run `gh pr list` or open the Pull
requests tab.

**How do I take over a task someone handed off?**
Run `/claim-task` and name the PR. Their notes are under "Handoff" in
`docs/tasks/<branch>.md`.

**My commit was blocked by "Detect hardcoded secrets".**
Take the secret out of the file. Put it in `.env` (ignored by git) or your AWS profile, then
commit again. If it was already pushed, rotate it. Don't use `--no-verify`.

**My commit failed with "files were modified by this hook".**
ruff fixed the formatting for you. Run `git add` on those files and commit again.

**"check for added large files" failed.**
Documents and data go in S3, not git.

**`/create-pr` stopped because review found "hard" issues.**
Ask your AI to fix them, then run `/create-pr` again. If you think a finding is wrong, say
why and tell it to go ahead.

**`main` changed while I was working.**
`/create-pr` merges the latest `main` into your branch. If there are conflicts, it works
through them with you.

**How does my PR get merged?**
A teammate (or you) reads it on GitHub and clicks Merge. AI agents never merge.

**Can I change my own Claude or Codex settings, MCP servers, or add personal skills?**
Yes. Put them in `CLAUDE.local.md`, `AGENTS.override.md`, `.claude/settings*.json`,
`.mcp.json`, `.codex/`, or your home folder (`~/.claude`, `~/.codex`). Git ignores all of
these. Changes to the shared skills or `AGENTS.md` go through a PR.

**AWS says "Unable to locate credentials" or "ExpiredToken".**
Sandbox credentials expire. Run `aws sso login`, or export fresh sandbox credentials, then
run `/setup` again.

**Bedrock says a model isn't available in my region.**
Use the model's cross-region inference profile ID (it starts with `us.`, `eu.` or
`global.`) instead of the plain model ID.

**I'm on Windows and the skills don't show up in Claude Code.**
`.claude/skills` is a symlink, which Windows only creates if Developer Mode is on. Turn on
Developer Mode, run `git config --global core.symlinks true`, and clone again. Or use WSL.
