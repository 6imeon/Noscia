-- Runs once on first cluster init (docker-entrypoint-initdb.d).
-- ParadeDB bundles both extensions; we still have to CREATE them in the DB.
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector: dense ANN (HNSW, <=> cosine)
CREATE EXTENSION IF NOT EXISTS pg_search;  -- ParadeDB: true BM25 full-text
