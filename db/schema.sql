-- AskWRI tables and indexes on askwri-db. Safe to rerun: python3 db/apply_schema.py
-- Statements end with ";" at the end of a line; the apply script splits on that.
-- Columns follow the ingestion pipeline's records (askwri/ingest: Chunk and the catalog row),
-- so its output loads without renaming; db/load.py does the mapping.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
  doc_id text PRIMARY KEY,            -- the ingestion pipeline's document ID
  title text NOT NULL,
  url text,                           -- wri.org page, checked to resolve ("link" in ingestion)
  doi text,                           -- the document's own WRI DOI, when it prints one
  file_sha256 text UNIQUE NOT NULL,   -- always stored, to catch the same PDF arriving twice
  pdf_key text NOT NULL,              -- S3 key of the stored PDF in the corpus bucket (raw/...)
  year int,
  pub_date date,
  date_source text NOT NULL CHECK (date_source IN ('wri.org', 'manifest', 'printed', 'file_metadata', 'none')),
  date_confidence text NOT NULL CHECK (date_confidence IN ('high', 'low', 'undated')),
  pub_type text,                      -- WRI's type (Report, Issue brief, ...) or the labeler's reading
  office text,                        -- WRI (global), WRI Brasil, WRI México, ...
  topic text,                         -- one of WRI's 11 topics, or 'none'
  topic_source text,                  -- 'wri.org' or 'model'
  label_source text NOT NULL,         -- where the labels came from: 'wri.org', 'model' or 'no page'
  tags text[] NOT NULL DEFAULT '{}',  -- secondary tags: search filters, never counts
  countries text[] NOT NULL DEFAULT '{}',
  authors text[] NOT NULL DEFAULT '{}',
  summary text,
  language text                       -- ISO 639-1, e.g. 'en', 'es', 'pt'; null until detected
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id text PRIMARY KEY,          -- "<doc_id>#p<pdf page>-<position on page>"
  doc_id text NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  seq int NOT NULL,                   -- position in the document's chunk order, from 1
  page int NOT NULL,                  -- PDF page where the chunk starts (opens the PDF there)
  page_end int NOT NULL,
  printed_page text NOT NULL,         -- number printed on the page ("iv", "12"), for display
  printed_page_end text NOT NULL,
  printed_page_fallback boolean NOT NULL DEFAULT false,  -- true: no printed number was found
  section text NOT NULL DEFAULT '',   -- section path, e.g. "Supply risks › Lithium"
  kind text NOT NULL DEFAULT 'source_text',  -- source_text, table, chart or image
  quotable boolean NOT NULL DEFAULT true,    -- false: cite the page, never quote verbatim
  address text NOT NULL,              -- "document title › section", so a passage stands alone
  content text NOT NULL,              -- the passage itself: what citations quote
  embedding vector(1024),             -- of address + content; must equal embedding_dim
  -- Keyword search covers the address too, so title and section words match.
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', address || ' ' || content)) STORED,
  UNIQUE (doc_id, seq)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS documents_filters_idx ON documents (year, pub_type, topic, language);
CREATE INDEX IF NOT EXISTS documents_countries_idx ON documents USING gin (countries);

CREATE TABLE IF NOT EXISTS translations (
  hash text PRIMARY KEY,              -- SHA-256 of target language + source text
  lang text NOT NULL,
  text text NOT NULL
);

-- App users sign in with IAM database authentication, so no app password exists anywhere.
DO $$ BEGIN CREATE ROLE askwri_ingest LOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE askwri_tools LOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
GRANT rds_iam TO askwri_ingest, askwri_tools;

GRANT SELECT, INSERT, UPDATE, DELETE ON documents, chunks TO askwri_ingest;
GRANT SELECT ON documents, chunks TO askwri_tools;
GRANT SELECT, INSERT, UPDATE ON translations TO askwri_tools;
