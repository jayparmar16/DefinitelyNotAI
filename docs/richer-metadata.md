# Richer document metadata: what changed and how to test it

Branch `richer-metadata` (task: [docs/tasks/richer-metadata.md](tasks/richer-metadata.md)).
The existing tests were updated for the new model calls, and one test covers the wri.org
taxonomy line; the labels themselves have no tests, as agreed. This page is the manual
test plan.

## Why

On 4 Nov, "What are the trends for ocean renewable energies published in 2025?" returned
2 passages, both from one paper:

- 341 of 562 documents had no `year`, so a 2025 filter hid them.
- *Impact Assessment of Offshore Wind Energy Projects in India* (Feb 2025) is labelled
  Energy only. Its wri.org page says it is "part of Ocean Climate Diplomacy", but ingestion
  threw that line away.
- 23 of the 25 candidates came from one document, and 9 of the 25 were References,
  Contents or Endnotes chunks.

## What changed

| Field | Table | Where it comes from | Model? |
|---|---|---|---|
| `year`, `date_source` | documents | publication date (wri.org or labeler), else the corpus folder (`2025/x.pdf`) | no |
| `abstract` | documents | wri.org page `description` meta tag | no |
| `initiatives`, `programs` | documents | wri.org "This ... is part of X within Y" line (link texts) | no |
| `topics` | documents | at most 2: `topic` first, then a WRI tag that is one of the 11, else the labeler's second | partly |
| `concepts` | documents | WRI tags in `askwri/ingest/vocabulary.py` CONCEPTS (case-insensitive), then the labeler's | partly |
| `acronyms` | documents | "Long form (SHORT)" in the text, e.g. `OSW = Offshore wind` | no |
| `role` | chunks | section path: references, notes, contents, acknowledgements, about, abbreviations | no |
| `keywords`, `regions`, `key_findings`, `genre`, `coverage_start`, `coverage_end` | documents | one `labeler` call per document | yes |
| `countries` | documents | existing labeler countries, plus the enrichment call's | yes |
| `doc_tsv`, `card_embedding` | documents | the document card (title, abstract or summary, labels, key findings), plus acronyms in `doc_tsv` | built from the above |
| context line in each chunk's embedding | chunks (`embedding`) | year, topics, first 6 concepts, initiatives, first 6 places | built from the above |

The labeler's answers can differ between runs. Capping topics at two and asking only for
regions a document is about made topics and regions the same in three runs of both test
PDFs; the tail of `concepts` and `keywords` still varies a little.

Rules kept from before: model labels never replace WRI's (they are appended), `tags` keeps
WRI's original tags, `topic` stays the single counted topic, and model-written text
(`key_findings`, the card) is for search only and never quoted.

Search changes in this branch: `askwri/search.py` skips chunks with a `role`. Nothing
else in search reads the new fields yet (see "Not in this branch").

## Before you start

1. Credentials. `db/query.py` reads `.env` itself. For the other commands, load `.env`
   into the shell first:

   ```sh
   set -a; . ./.env; set +a
   ```

2. Check the labeler model with these credentials:

   ```sh
   uv run python -m askwri.models smoke      # expect PASS for labeler
   ```

3. Corpus folders are named for their year: `2024`, `2025`, `2026` (`2025_publications`
   also works; the name has to start with the year). A folder named anything else leaves
   undated documents undated.

4. Cost of a full reload. The first load on a machine makes every model call; it saves
   each reply in `.cache/ingest/model-calls/`, and later loads replay them. With today's corpus that is about 562 enrichment
   calls, about 3,070 table summaries (tables with a role are no longer summarized) and
   about 386 fallback-label calls, all on the `labeler` (Haiku, at effort `low`). Table
   summaries run 4 at a time per document. It also makes about 694 Cohere embedding calls
   (batches of 96 per document, now including its card) and fetches the wri.org pages again.

## Step 1: one PDF locally, no Aurora

This shows every new label and the context line without touching the database.

```sh
mkdir -p /tmp/try/2025
cp <corpus>/2025/environmental-socio-economic-impact-assessment-offshore-wind-energy-projects-india.pdf /tmp/try/2025/
cp <corpus>/2025/<an undated pdf, e.g. a newsletter or RFP>.pdf /tmp/try/2025/
uv run python -m askwri.ingest /tmp/try/2025/*.pdf --out /tmp/try/out
```

Check `/tmp/try/out/catalog.json`. For the offshore wind paper, expect:

- `year` 2025 and `date_source` `wri.org`.
- `initiatives` `["Ocean Climate Diplomacy"]` and `programs` `["Energy", "Clean Energy"]`.
- `abstract` starting "Offshore wind (OSW) projects are a new source of renewable energy...".
- `topics` `["Energy", "Ocean"]`: at most two, `Ocean` added by the labeler.
- `concepts` including `Clean Energy` and `renewable energy` from WRI's tags, then the
  labeler's.
- `acronyms` including `OSW = Offshore wind` if the PDF defines it the way its abstract does.
- `keywords`, `regions` (expect `South Asia`), 3 to 5 `key_findings`, a `genre` and
  `coverage_start`/`coverage_end` filled.

For the undated PDF, expect `year` 2025 and `date_source` `folder`.

Check the context line: open any `/tmp/try/out/<doc_id>/p*.txt`. The first paragraph is the
address (title › section), and the second is the context line, for example
`2025 · Energy, Ocean · Clean Energy, renewable energy, offshore wind · Ocean Climate Diplomacy · India, South Asia`.
A chunk under References or Contents has `"role"` in its `.metadata.json`.

## Step 2: a few PDFs into Aurora

The schema change only adds nullable columns, so main's code keeps working against the
upgraded database. Apply it before running this branch's search, which reads `chunks.role`.

```sh
uv run python db/apply_schema.py
export CORPUS_BUCKET="askwri-corpus-$(aws sts get-caller-identity --query Account --output text)"
uv run python -m askwri.ingest.load --reload /tmp/try/2025
```

This replaces the rows of those documents only. Each `LOADED` line now ends with the year,
its source and the topics. Run the SQL checks below on those `doc_id`s. Sorting only sees
the folder you pass, so those documents' `replaces` lists (older versions dropped) may be
shorter until the full reload.

## Step 3: the whole corpus

```sh
scripts/run-pipeline.sh 2024_publications 2025_publications 2026_publications
```

No `--reload` is needed: a document loaded before this branch has no `card_embedding`, so it
counts as not loaded. If the run stops (expired session credentials, a closed laptop),
refresh `.env` and run the same command again: it loads only the documents not yet done.

Each document is replaced in its own transaction, so search keeps working during the
reload, over a mix of old and new rows until it ends. A document whose model call fails, or
whose topic, concept, region or genre is outside its list, is `SKIPPED` and keeps its old
rows; the run goes on. Rerun the same command to retry the skipped documents.

## SQL checks

Run each with `uv run python db/query.py "<sql>"`.

**Dates.** No document should be undated, unless a folder name doesn't start with a year.

```sql
SELECT date_source, count(*) AS docs, min(year), max(year) FROM documents GROUP BY 1 ORDER BY 1
```

Expect `folder` at about 341 (the documents undated before), `wri.org` at about 176,
`model` for the rest, and no null row.

**wri.org fields.**

```sql
SELECT count(*) AS wri_docs, count(abstract) AS with_abstract,
  count(*) FILTER (WHERE cardinality(initiatives) > 0) AS with_initiatives
FROM documents WHERE label_source = 'wri.org'
```

Expect `with_abstract` close to `wri_docs`. `with_initiatives` should be most of them: all
7 pages sampled had the line.

**The offshore wind paper.**

```sql
SELECT year, date_source, initiatives, programs, topics, concepts, acronyms, regions, genre
FROM documents WHERE doc_id = 'environmental-socio-economic-impact-assessment-offshore-wind-energy-projects-india'
```

**Topics and concepts across the corpus.**

```sql
SELECT t AS topic, count(*) FROM documents, unnest(topics) t GROUP BY 1 ORDER BY 2 DESC
```

```sql
SELECT c AS concept, count(*) FROM documents, unnest(concepts) c GROUP BY 1 ORDER BY 2 DESC LIMIT 40
```

**WRI's labels were not replaced.** Expect 0.

```sql
SELECT count(*) FROM documents WHERE topic IS NOT NULL AND topic <> 'none' AND topics[1] IS DISTINCT FROM topic
```

**Enrichment filled every document.** Expect each count to be close to `docs`;
`with_coverage` will be lower, because many documents don't say.

```sql
SELECT count(*) AS docs, count(genre) AS with_genre,
  count(*) FILTER (WHERE cardinality(key_findings) > 0) AS with_findings,
  count(*) FILTER (WHERE cardinality(keywords) > 0) AS with_keywords,
  count(*) FILTER (WHERE cardinality(regions) > 0) AS with_regions,
  count(coverage_start) AS with_coverage,
  count(card_embedding) AS with_card, count(doc_tsv) AS with_doc_tsv
FROM documents
```

```sql
SELECT genre, count(*) FROM documents GROUP BY 1 ORDER BY 2 DESC
```

**Chunk roles.** First the counts, then spot-check that every role chunk really is
apparatus, then look for headings the rules missed.

```sql
SELECT coalesce(role, '(content)') AS role, count(*) FROM chunks GROUP BY 1 ORDER BY 2 DESC
```

```sql
SELECT role, section FROM chunks WHERE role IS NOT NULL ORDER BY random() LIMIT 25
```

```sql
SELECT section, count(*) FROM chunks
WHERE role IS NULL AND section ~* '(reference|endnote|contents|acknowledg|abbreviation|acronym)'
GROUP BY 1 ORDER BY 2 DESC LIMIT 25
```

The last query lists sections whose heading contains those words but did not get a role,
for example "Climate references in NDCs". Add a heading to `SECTION_ROLES` in
`askwri/ingest/chunks.py` if one should have.

**The document keyword index.** 2025 documents about ocean energy:

```sql
SELECT doc_id, round(ts_rank(doc_tsv, q)::numeric, 3) AS rank
FROM documents, to_tsquery('english', '(offshore <-> wind) | tidal | (wave <-> energy) | (ocean <-> energy) | (ocean & renewable)') q
WHERE doc_tsv @@ q AND year = 2025 ORDER BY rank DESC
```

**The document card embedding.** The documents closest to the offshore wind paper:

```sql
SELECT d.doc_id, d.year, round((d.card_embedding <=> o.card_embedding)::numeric, 3) AS distance
FROM documents d, documents o
WHERE o.doc_id = 'environmental-socio-economic-impact-assessment-offshore-wind-energy-projects-india'
ORDER BY distance LIMIT 10
```

Expect ocean, offshore and renewable-energy documents near the top.

## The example question, before and after

```sh
uv run python -m askwri.search "What are the trends for ocean renewable energies published in 2025?"
uv run python -m askwri.search "What are the trends for ocean renewable energies published in 2025?" --year-from 2025 --year-to 2025
```

To see the 25 candidates the reranker gets (on 4 Nov: 2 documents, 23 from one, 9
apparatus chunks):

```sh
uv run python - <<'EOF'
import json
from askwri import search as s
q = "What are the trends for ocean renewable energies published in 2025?"
aws = s._aws()
params = {"q": q, "vec": json.dumps(s._embed_query(aws["bedrock"], q)), "year_from": None,
          "year_to": None, "topic": None, "doc_type": None, "country": None}
rows = s._query_hybrid(aws["data_api"], aws["target"], params)
print(len(rows), "candidates from", len({r["doc_id"] for r in rows}), "documents")
for r in rows:
    print(r["doc_id"][:70], "|", (r["section"] or "")[-50:])
EOF
```

What to expect: no References, Contents or Endnotes chunks, and more 2025 documents in the
year-filtered run. The keyword half of search still requires every word of the question,
so it still matches nothing for this wording. Any gain on this question comes from the
context line in the embeddings. The query-side fixes are not in this branch.

## Not in this branch

These are the query-side ideas (D):

- A small-model query step that turns a question into keywords, synonyms and filters.
- An OR-based keyword query in place of all-words.
- A per-document cap on candidates.
- Two-stage search (documents first through `doc_tsv` and `card_embedding`, then passages).
- Search filters on `topics`, `concepts` and `regions`.
- Synonym expansion from `acronyms`.

Until then, the new document-level fields are stored and checkable by SQL but unused by
`search_passages()`. There are no GIN indexes on the new arrays or on `doc_tsv`; 562 rows
don't need them, and D can add them with the queries that use them.

## Undo

The new columns are nullable, and main's code never reads them, so main works against the
upgraded database as it is. There is no down-migration. If needed, drop the columns by hand
with `ALTER TABLE documents DROP COLUMN ...` and `ALTER TABLE chunks DROP COLUMN role`. Rows
reloaded by this branch keep their context-line embeddings until they are loaded again.
