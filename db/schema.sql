-- AskWRI tables and indexes on askwri-db. Safe to rerun: python3 db/apply_schema.py
-- Statements end with ";" at the end of a line; the apply script splits on that.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
  doc_id text PRIMARY KEY,            -- slug of the PDF's file name, e.g. "critical-minerals-india"
  file_sha256 text UNIQUE NOT NULL,
  pdf_key text NOT NULL,              -- S3 key of the stored PDF: the citation fallback
  title text NOT NULL,
  label_source text NOT NULL,         -- 'wri.org', 'model' or 'no page'
  url text,                           -- checked wri.org page
  doi text,
  topic text,                         -- one of the 11 topics, 'none', or null
  topic_source text,                  -- 'wri.org' or 'model'
  wri_type text,                      -- WRI's own type (Research, Data)
  doc_type text NOT NULL,             -- the sorter's type
  pub_date date,
  year int,
  authors text[],
  tags text[],
  countries text[],
  summary text,
  deadline date,                      -- RFPs
  language text,
  replaces text[]                     -- older versions the sorter dropped
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id text PRIMARY KEY,          -- "<doc_id>#p<start page>-<n>"
  doc_id text NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  seq int NOT NULL,                   -- position in the document, for neighbour fetches
  kind text NOT NULL,                 -- 'source_text', 'table', 'chart' or 'image'
  pdf_page int NOT NULL,
  pdf_page_end int NOT NULL,
  printed_page text NOT NULL,         -- text: front matter uses Roman numerals
  printed_page_end text NOT NULL,
  printed_page_fallback boolean NOT NULL,
  section text,
  content text NOT NULL,              -- the passage; table rows for tables
  description text,                   -- model-written summary: searchable, never quoted
  number text,                        -- table or figure number
  figure_key text,                    -- S3 key of the figure image
  quotable boolean NOT NULL,          -- false: cite the page, never quote verbatim
  embedding vector(1024) NOT NULL,    -- Cohere Embed v4 of "title > section" + content/description
  tsv tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', content || ' ' || coalesce(description, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(section, '')), 'B')
  ) STORED
);

-- Richer labels (docs/tasks/richer-metadata.md). ADD COLUMN IF NOT EXISTS upgrades a database
-- created before them in place; `python -m askwri.ingest.load --reload` fills them.
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS date_source text,    -- source of `year`: 'wri.org', 'model', 'folder'
  ADD COLUMN IF NOT EXISTS abstract text,       -- the wri.org page's description: WRI's words
  ADD COLUMN IF NOT EXISTS initiatives text[],  -- the page's "part of ... within ..." line
  ADD COLUMN IF NOT EXISTS programs text[],
  ADD COLUMN IF NOT EXISTS topics text[],       -- every topic covered, `topic` (counted) first
  ADD COLUMN IF NOT EXISTS concepts text[],     -- askwri/ingest/vocabulary.py CONCEPTS
  ADD COLUMN IF NOT EXISTS keywords text[],     -- the labeler's search phrases
  ADD COLUMN IF NOT EXISTS acronyms text[],     -- 'OSW = Offshore wind', as the text defines them
  ADD COLUMN IF NOT EXISTS regions text[],      -- vocabulary.py REGIONS
  ADD COLUMN IF NOT EXISTS key_findings text[], -- model-written: searchable, never quoted
  ADD COLUMN IF NOT EXISTS genre text,          -- vocabulary.py GENRES
  ADD COLUMN IF NOT EXISTS coverage_start int,  -- the years the document's data covers
  ADD COLUMN IF NOT EXISTS coverage_end int,
  ADD COLUMN IF NOT EXISTS doc_tsv tsvector,    -- keyword index: document card and acronyms
  ADD COLUMN IF NOT EXISTS card_embedding vector(1024);  -- Cohere Embed v4 of the card

-- 'references', 'notes', 'contents', 'acknowledgements', 'about' or 'abbreviations', from the
-- section path. Null for the document's own content. Search skips chunks with a role.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS role text;

CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS chunks_doc_seq_idx ON chunks (doc_id, seq);
CREATE INDEX IF NOT EXISTS documents_filters_idx ON documents (year, topic, doc_type);

CREATE TABLE IF NOT EXISTS translations (
  hash text PRIMARY KEY,              -- SHA-256 of target language + source text
  lang text NOT NULL,
  text text NOT NULL
);

-- Which WRI documents in the collection cite which others, found by python -m askwri.links:
-- a DOI, wri.org link or title of one document appearing in another's text.
CREATE TABLE IF NOT EXISTS citations (
  src_doc_id text NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,  -- the citing document
  dst_doc_id text NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,  -- the cited one
  match_method text NOT NULL,         -- doi, url or title
  chunk_id text,                      -- passage of the citing document where it appears
  context_sentence text,              -- the sentence (or reference entry) that mentions it
  context_page int,                   -- PDF page of that sentence
  relation text,                      -- extends, uses_data_or_method, supports, contrasts, updates, background
  aspect text,                        -- what of the cited document is used, in a few words
  confidence real,                    -- 0-1; at most 0.4 when only a reference entry was found
  PRIMARY KEY (src_doc_id, dst_doc_id)
);
CREATE INDEX IF NOT EXISTS citations_dst_idx ON citations (dst_doc_id);

-- What the agent's tools read: the pipeline's rows plus the fields they derive. Views, so the
-- ingestion pipeline's tables stay exactly as askwri.ingest.load writes them.
-- Dropped and recreated: d.* and c.* grow when the pipeline adds columns, and CREATE OR REPLACE
-- cannot move a view's existing columns.
DROP VIEW IF EXISTS chunks_v;
DROP VIEW IF EXISTS documents_v;

CREATE VIEW documents_v AS
SELECT d.*,
  -- WRI DOIs name the publication type: 10.46830/wriwp.25.00035 is a working paper.
  CASE
    WHEN d.doi ~ '^10\.46830/wrirpt\.' THEN 'Report'
    WHEN d.doi ~ '^10\.46830/wriwp\.' THEN 'Working paper'
    WHEN d.doi ~ '^10\.46830/writn\.' THEN 'Technical note'
    WHEN d.doi ~ '^10\.46830/wriib\.' THEN 'Issue brief'
    WHEN d.doc_type = 'research report' THEN 'Report'
    WHEN d.doc_type IS NOT NULL AND d.doc_type <> 'other' THEN upper(left(d.doc_type, 1)) || substr(d.doc_type, 2)
    ELSE d.wri_type
  END AS pub_type,
  -- date_source is the pipeline's: 'wri.org', 'model' (printed in the document) or 'folder'.
  CASE
    WHEN d.year IS NULL THEN 'undated'
    WHEN d.date_source = 'wri.org' THEN 'high'
    ELSE 'low'
  END AS date_confidence,
  NULL::text AS office
FROM documents d;

CREATE VIEW chunks_v AS
SELECT c.*, c.pdf_page AS page, c.pdf_page_end AS page_end,
  d.title || CASE WHEN coalesce(c.section, '') = '' THEN '' ELSE ' › ' || c.section END AS address
FROM chunks c JOIN documents d USING (doc_id);

-- App users sign in with IAM database authentication, so no app password exists anywhere.
DO $$ BEGIN CREATE ROLE askwri_ingest LOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE askwri_tools LOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
GRANT rds_iam TO askwri_ingest, askwri_tools;

GRANT SELECT, INSERT, UPDATE, DELETE ON documents, chunks TO askwri_ingest;
GRANT SELECT ON documents, chunks, citations, documents_v, chunks_v TO askwri_tools;
GRANT SELECT, INSERT, UPDATE, DELETE ON citations TO askwri_ingest;
GRANT SELECT, INSERT, UPDATE ON translations TO askwri_tools;
