-- Noscia Phase 1 schema. Canonical DDL — idempotent, so it serves double duty:
--   * fresh containers run it once at initdb (after 01-extensions.sql), and
--   * the app re-applies it on startup via noscia.db.init_schema().
-- Keep every statement IF NOT EXISTS / idempotent so re-running is a no-op.

-- chunks: the search corpus. One row per ~512-token passage.
CREATE TABLE IF NOT EXISTS chunks (
    id            TEXT PRIMARY KEY,                 -- position-stable: sha256(url#ordinal), so a recrawl diffs content_hash in place
    url           TEXT        NOT NULL,             -- the page this chunk came from (citation target)
    source_url    TEXT,                             -- the seed this page was discovered under (deep crawl); enables source-level page pruning
    title         TEXT        NOT NULL DEFAULT '',
    org           TEXT,
    source_type   TEXT        NOT NULL,             -- contract SourceType literal
    text          TEXT        NOT NULL,
    content_hash  TEXT        NOT NULL,             -- sha256 of normalized text (Phase 2 incremental crawl)
    token_count   INTEGER,
    dense         vector(256) NOT NULL,             -- Qwen3 → Matryoshka 256, L2-normalized
    industry      TEXT        NOT NULL DEFAULT 'esg', -- the vertical this chunk belongs to; every retrieval filters WHERE industry = :active (MULTI_INDUSTRY.md §5.1)
    crawled_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ                        -- when the *document* was published (NULL = unknown); ≠ crawled_at. Evidence-or-null: only set when a date is found in page/PDF metadata
);

-- Deep crawl (Phase 2.5): a seed expands to many same-domain pages; source_url ties
-- each chunk back to its seed so a vanished page's chunks can be pruned source-wide.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS source_url TEXT;

-- Phase 2 recency: document publication date, extracted from HTML head meta / PDF
-- metadata at ingest. Nullable — a missing date never penalizes (the news-weighted
-- recency prior treats un-dated chunks as a no-op). Added to pre-existing tables too.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

-- Multi-industry (MULTI_INDUSTRY.md): the vertical a chunk belongs to. DEFAULT 'esg'
-- backfills every pre-existing row in place (no data move) — the migration *is* the
-- default. Every retrieval CTE filters `WHERE industry = :industry`; the btree index
-- keeps that filter cheap and is the seam the partitioning upgrade (§5.1) builds on.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS industry TEXT NOT NULL DEFAULT 'esg';
CREATE INDEX IF NOT EXISTS chunks_industry_idx ON chunks (industry);

-- Dense ANN: HNSW over cosine distance (pgvector). `<=>` is cosine distance.
CREATE INDEX IF NOT EXISTS chunks_dense_hnsw
    ON chunks USING hnsw (dense vector_cosine_ops);

-- Lexical: ParadeDB pg_search BM25 over text + title, keyed by id.
CREATE INDEX IF NOT EXISTS chunks_bm25
    ON chunks USING bm25 (id, text, title)
    WITH (key_field = 'id');

CREATE INDEX IF NOT EXISTS chunks_url_idx ON chunks (url);
CREATE INDEX IF NOT EXISTS chunks_source_url_idx ON chunks (source_url);

-- sources: one row per seed URL — powers the Corpus view (status, counts, cadence).
CREATE TABLE IF NOT EXISTS sources (
    url          TEXT PRIMARY KEY,
    source_type  TEXT        NOT NULL,
    org          TEXT,
    industry     TEXT        NOT NULL DEFAULT 'esg',  -- the vertical this seed feeds; scopes the Corpus view and crawls
    cadence      TEXT        NOT NULL DEFAULT 'monthly',
    status       TEXT        NOT NULL DEFAULT 'idle',   -- idle | crawling | done | error
    pages        INTEGER     NOT NULL DEFAULT 0,
    chunks       INTEGER     NOT NULL DEFAULT 0,
    last_crawl   TIMESTAMPTZ,
    error        TEXT,
    -- Phase 2 incremental crawl: HTTP validators echoed back as If-None-Match /
    -- If-Modified-Since so an unchanged page short-circuits with a 304 (no re-crawl).
    etag          TEXT,
    last_modified TEXT
);

-- Phase 2 columns are added to pre-existing `sources` tables too (idempotent).
ALTER TABLE sources ADD COLUMN IF NOT EXISTS etag          TEXT;
ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_modified TEXT;

-- Multi-industry: tag each seed with its vertical (DEFAULT 'esg' backfills in place).
ALTER TABLE sources ADD COLUMN IF NOT EXISTS industry TEXT NOT NULL DEFAULT 'esg';
CREATE INDEX IF NOT EXISTS sources_industry_idx ON sources (industry);

-- user_prefs: per-user product state (MULTI_INDUSTRY.md §5.4). Today just the active
-- vertical — "loaded one at a time" is this row, not a physical data swap. Keyed by
-- User.id (SoloUser → 'solo'); when SSO lands the key becomes the SSO user with no
-- call-site change (same seam as user.py::current_user).
CREATE TABLE IF NOT EXISTS user_prefs (
    user_id          TEXT PRIMARY KEY,
    active_industry  TEXT        NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
