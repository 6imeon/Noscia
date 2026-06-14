# Changelog

All notable changes to Noscia are recorded here. Updated at the **end of each phase**
(see [IMPLEMENTATION.md](IMPLEMENTATION.md) §7). Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); dates are absolute.

## Phase 2 — Quality + freshness — 2026-06-14

Two halves landed: an **eval gate** for every model change, and **incremental
freshness** so recrawls are cheap. The fine-tune pipeline is built, runs locally on
an 18 GB machine, and is **honestly eval-gated** — it does not ship because the demo
corpus is too small for the eval to show a win (see note). Live-search fallback is
deferred by decision.

### Eval harness (`server/src/noscia/train/eval.py`)
- `corpus/eval/esg_queries.jsonl` — 15 held-out ESG queries with **URL-level relevance**
  grounded in the actually-indexed text (no query sees its own training signal).
- nDCG@10 / MRR / Recall@10 over a deduped URL ranking; a *retriever* is just
  `(query, k) → ranked URLs`, so base-vs-fine-tuned compare on the same set/metrics.
  Built-in retrievers wrap the live Quality + Fast tiers. `--per-query` breakdown.
- **Honest finding:** on the 8-doc demo corpus retrieval is near-saturated
  (nDCG@10 ≈ 0.99, MRR/Recall = 1.000) — so per rule 9 no fine-tune can be *justified*
  here yet. The gate is real even when the corpus makes the result a tie.

### Incremental crawl (`server/src/noscia/ingest/`)
- **Conditional probe** (`crawl.py::check_conditional`) — a streamed `If-None-Match` /
  `If-Modified-Since` GET; a `304` skips the browser render entirely (proven live).
- **Content-hash diff** (`run.py`) — only changed/new chunks are re-embedded, vanished
  chunks pruned, unchanged chunks left untouched (a recrawl re-embedded **0** of 4).
  Chunk ids are position-stable (`sha256(url#ordinal)`) so the diff lands in place.
- **Adaptive cadence** — `corpus.sources_due()` maps each source's cadence (hourly …
  monthly) to a window; `ingest_due()` / `--due` recrawls only what's stale.
- `sources` gains `etag` / `last_modified` (idempotent `ALTER … IF NOT EXISTS`).

### Fine-tune pipeline (`server/src/noscia/train/`, `train` dep group)
- `synth.py` — BYOK LLM (OpenRouter via `get_secret`, never a raw key in source)
  writes ~3–5 synthetic queries per chunk → `data/train/synth_pairs.jsonl` (gitignored).
- `finetune.py` — **LoRA** fine-tune of Qwen3-0.6B (MNRL wrapped in MatryoshkaLoss at
  the deployed 256-dim prefix) + gradient checkpointing + capped batch/seq, so it trains
  in ~1 min on 18 GB unified memory with **no** MPS watermark override. Then re-runs the
  ESG eval base-vs-fine-tuned and prints the verdict — **ship only if it wins** (rule 9).
- This run: fine-tuned ties base (Δ nDCG = +0.000, saturated) → **DO NOT SHIP**, as
  expected. The adapter verifiably changes the model (cos(base, ft) = 0.988); the tie is
  real, not a no-op.

### Deferred (decision, not silent skip)
- **Live-search fallback** (BYOK Exa/Tavily/Firecrawl for out-of-corpus / low-confidence
  queries) — deferred; revisit later.
- ColBERT + MUVERA late-interaction path — optional; only if it beats single-vector on eval.

### Pinned versions
- httpx 0.28.1 (conditional probe + BYOK calls). `train` group (offline,
  `uv sync --group train`): datasets 5.0.0 · accelerate 1.13.0 · peft 0.19.1.

## Phase 1 — Core ESG search — 2026-06-14

The crawl → index → search pipeline is live end to end. An ESG question returns
relevant, highlighted, cited passages from the local index — verified through the
Vite proxy the browser uses. Built thin (8 curated seeds, 37 chunks) per the
"thin end-to-end first" rule.

### Ingestion (`server/src/noscia/ingest/`)
- `corpus/seeds.esg.yaml` — 8 curated ESG seeds (GHG Protocol, GRI, TCFD, IFRS S2,
  EU CSRD, MSCI, SBTi, CDP) grouped by `source_type` + recrawl cadence.
- `crawl.py` — crawl4ai 0.8.9 (headless Chromium) → clean markdown + title; per-URL
  error capture so one dead seed never sinks a run.
- `chunk.py` — tiktoken-accurate ~512-token windows (64 overlap) with a `content_hash`
  per chunk (for Phase 2 incremental crawl); strips markdown link/image/nav soup so
  passages read clean.
- `run.py` — the ingest runner + `python -m noscia.ingest.run` CLI; delete-by-url then
  upsert so a re-crawl never leaves stale chunks. Source status walks idle → crawling → done/error.

### Search (`server/src/noscia/search/`)
- `embed.py` — Qwen3-Embedding-0.6B via sentence-transformers; query-instruction vs raw-doc
  asymmetry; **Matryoshka** truncation 1024→256 + renormalize. Lazy-loaded, MPS/CUDA/CPU auto.
- `store.py` — `PgVectorStore` (the one `VectorStore` impl): `ON CONFLICT` upsert and the
  **hybrid RRF query in one Postgres round-trip** — dense CTE (pgvector `<=>`) + BM25 CTE
  (`pg_search` `@@@`), fused with Reciprocal Rank Fusion in SQL.
- `rerank.py` — `bge-reranker-v2-m3` cross-encoder over the fused top-50 (sigmoid-squashed scores).
- `highlight.py` — best-matching passage per result with `<mark>` spans; crawled HTML escaped
  before marking (no passage can inject markup).
- `pipeline.py` — the two tiers: **Quality** (embed → hybrid → rerank → highlight) and **Fast**
  (embed → dense-only ANN → highlight); returns the contract `SearchResponse` with the pipeline trace.

### Datastore
- `db/init/02-schema.sql` — `chunks` (`vector(256)` HNSW + `pg_search` bm25 index, content-addressed id)
  and `sources` (Corpus view state). Idempotent; applied at initdb and re-applied on startup via `db.init_schema()`.

### API + contract
- `/search` now runs the real pipeline. New `/corpus`, `/corpus/ingest`, `/corpus/add` endpoints.
- `contract.py` ⇄ `web/src/lib/api.ts` extended in lockstep: `CorpusStats`, `CorpusSource`,
  `CorpusResponse`, `AddSeedRequest`, `IngestRequest/Response`.
- App startup (lifespan) ensures schema + registers seeds idempotently.

### Frontend (`web/`)
- **Search view** fully wired: result list (`ResultRow` — #rank, source badge, `ScoreBar`,
  org·host, `<mark>` snippet, ● fresh) + split-pane `PassageReader` (source pill, meta strip,
  Highlighted↔Full-context toggle, Cite/Open actions). Empty/loading/error/done states.
- **Corpus view**: stat cards (chunks, pages, index size, model/dims) + sources table
  (status dot, counts, cadence, per-row recrawl) + add-&-crawl seed input.
- `SourceType` badge/dot maps the `source_type` string to the §8.2 color tokens (single source of truth).

### Pinned versions
- crawl4ai 0.8.9 · sentence-transformers 5.5.1 · torch 2.12.0 · transformers 5.10.2 ·
  numpy 2.4.6 · tiktoken 0.13.0 · pyyaml 6.0.3. Cooldown now **persisted** in
  `pyproject.toml` (`[tool.uv] exclude-newer`) so every `uv` resolve honors the 7-day window.

### Deferred to Phase 2 (noted, not silently skipped)
- Live streaming crawl progress (Phase 1 ingest is synchronous with status transitions).
- Full-page context in the reader's "Full-context" mode (currently drops `<mark>` spans only).
- Embedder/reranker eval harness (nDCG@10 / MRR on `corpus/eval/esg_queries.jsonl`).

## Phase 0 — Skeleton + guardrails — 2026-06-14

First buildable skeleton. The crawl → index → search pipeline and the UI surfaces
are stubbed but not implemented (Phase 1+). Everything below is verified green.

### Repo structure (locked to industry standard before building)
- Backend adopted **PyPA src-layout**: package `noscia` at `server/src/noscia/`, run via `uvicorn noscia.app:app`.
- Renamed the secrets module `secrets.py` → **`config.py`** (the old name shadows the Python stdlib `secrets`).
- Added a root **`package.json`** (a pnpm workspace requires one), `tests/`, `ruff`, `.python-version`, `.editorconfig`, CI workflow, and a proprietary `LICENSE` placeholder.
- Updated SPEC §3 repo layout + IMPLEMENTATION path references to match.

### Backend (`server/`)
- FastAPI app (`noscia.app`) with `GET /health` (pings Postgres via `SELECT 1`), plus contract-valid stubs `POST /search` and `GET /providers`.
- `contract.py` — the stable HTTP contract (Pydantic models), mirrored 1:1 in the frontend.
- `config.py` — `get_secret()` + `mask()`; the only seam that reads `.env` / env (never `os.environ` in app code).
- `db.py` — single SQLAlchemy engine + `ping()`.
- `user.py` — `CurrentUser` seam (`SoloUser` now; `HeaderUser` for SSO later).
- `search/store.py` — `VectorStore` interface (`PgVectorStore` impl lands in Phase 1).
- Tests: `pytest` (7 passing), `ruff` clean. Deps locked with the 7-day cooldown (`uv lock --exclude-newer 2026-06-07`).

### Frontend (`web/`)
- Vite + React 19 + TS scaffold; **Tailwind v4** with the §8.2 espresso design tokens defined in `@theme` (single source of truth — no hard-coded hex).
- Shell: 62px icon **Rail** + view router; four view shells — Search (functional empty split-pane wired to `/search`), Entity, Corpus (placeholders), **Settings · BYOK** (masked provider status from `/providers`).
- Live `/health` status pill; typed API client `src/lib/api.ts` mirroring the contract.
- `vitest` + Testing Library (1 smoke test passing); `eslint` clean; production build green.
- Dev server pinned to **port 5180** (`strictPort`) to avoid the crowded 5173 default.

### Datastore
- `docker-compose.yml` runs **ParadeDB `0.24.0-pg17`** (Postgres 17 + `pgvector` + `pg_search`) for the dev loop and the deployment (dev == prod).
- `db/init/01-extensions.sql` creates `vector` + `pg_search` on first init — both verified live.

### Guardrails (baked in from day one)
- pnpm workspace with `minimumReleaseAge: 10080` (7-day release cooldown); `renovate.json` carries the same across npm/PyPI/Cargo.
- `.gitignore` covers `.env`, `data/`, caches; `.env.example` ships `OPENROUTER_API_KEY` + `DATABASE_URL`.
- No AI attribution in git; commits authored under the GitHub no-reply identity.

### Verified end-to-end
- Through the Vite proxy the browser uses (`:5180` → `:8000`): `/api/health` → `{"status":"ok","db":true}`, `/api/providers` returns masked OpenRouter status.
- All 15 Phase 0 checklist items (IMPLEMENTATION §7) ticked.
