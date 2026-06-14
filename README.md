# Noscia

A vertical, ESG-domain neural search app — Exa-style retrieval over a curated sustainability corpus, with cited passages and an agentic entity-search mode. A company-internal tool: self-hosted via Docker behind the company's SSO, one shared index. Runs locally (`uvicorn` + `pnpm dev`) for development.

## Documents

- **[SPEC.md](SPEC.md)** — what the product is and why (architecture, search pipeline, entity search, constraints).
- **[IMPLEMENTATION.md](IMPLEMENTATION.md)** — current build plan: verified stack research, hard constraints, phase-by-phase checklist, the selected frontend design (§8), and deployment targets (§9).
- **[CHANGELOG.md](CHANGELOG.md)** — what changed, updated at the end of each phase.
- **[design/mockups/](design/mockups/)** — interactive UI explorations. Selected direction: `design-1-research-console.html`.

## Status

Phase 2 (quality + freshness) in progress: an **eval gate** (nDCG@10 / MRR /
Recall@10 on a held-out ESG set), **incremental crawl** (HTTP 304 + content-hash diff,
adaptive cadence), and a LoRA **fine-tune pipeline** that runs locally and is honestly
eval-gated (no ship on the demo corpus — the eval is saturated). Search is **index-only**:
no third-party search providers, no external data egress (freshness comes from incremental
recrawl, not a live API). Phase 1 (core ESG search) — crawl → index → hybrid → rerank →
highlighted, cited results — is complete. See [CHANGELOG.md](CHANGELOG.md) and
[IMPLEMENTATION.md](IMPLEMENTATION.md) §7.

### Run the dev loop

```bash
docker compose up -d postgres                       # datastore (pgvector + pg_search)
cd server && uv sync && uv run crawl4ai-setup        # deps + Playwright Chromium (once)
uv run python -m noscia.ingest.run                   # crawl seeds → embed → index
uv run uvicorn noscia.app:app --reload               # API on :8000
pnpm install && pnpm dev                             # web on :5180 (proxies /api → :8000)
```

First search downloads the embedder (~600 MB) and reranker; models cache under `data/`.

Phase 2 tooling (from `server/`):

```bash
uv run python -m noscia.train.eval                  # retrieval eval (nDCG@10 / MRR / Recall@10)
uv run python -m noscia.ingest.run --due            # recrawl only sources past their cadence
uv sync --group train                               # fine-tune deps (offline only)
uv run --group train python -m noscia.train.synth                 # BYOK synthetic training pairs
uv run --group train python -m noscia.train.finetune --train --compare   # LoRA fine-tune, eval-gated
```

## Stack (planned)

React + TypeScript + Vite (pnpm) · Python + FastAPI · Postgres + pgvector + `pg_search` BM25 (one datastore) · crawl4ai · Qwen3-Embedding-0.6B · bge-reranker-v2-m3 · BYOK LLM providers.
