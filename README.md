# Noscia

A vertical, ESG-domain neural search app — Exa-style retrieval over a curated sustainability corpus, with cited passages and an agentic entity-search mode. A company-internal tool: self-hosted via Docker behind the company's SSO, one shared index. Runs locally (`uvicorn` + `pnpm dev`) for development.

## Documents

- **[SPEC.md](SPEC.md)** — what the product is and why (architecture, search pipeline, entity search, constraints).
- **[IMPLEMENTATION.md](IMPLEMENTATION.md)** — current build plan: verified stack research, hard constraints, phase-by-phase checklist, the selected frontend design (§8), and deployment targets (§9).
- **[CHANGELOG.md](CHANGELOG.md)** — what changed, updated at the end of each phase.
- **[design/mockups/](design/mockups/)** — interactive UI explorations. Selected direction: `design-1-research-console.html`.

## Status

Phase 2 (quality + freshness) in progress: an **eval gate** (nDCG@10 / MRR /
Recall@10 on a held-out ESG set, scored at source-domain level), **deep crawl** (each
authoritative domain is crawled in depth — bounded same-domain BFS — for a **578-page /
2,593-chunk** index across 21 sources, clean prose with cookie/consent boilerplate stripped),
**incremental crawl** (HTTP 304 + content-hash diff + page-level prune, adaptive
cadence), and a LoRA **fine-tune pipeline** that runs locally and is honestly eval-gated.
Search is **index-only**: no third-party search providers, no external data egress —
depth comes from crawling our 21 curated authoritative domains, never the open web (rule 13).
Phase 1 (core ESG search) — crawl → index → hybrid → rerank → highlighted, cited results —
is complete. See [CHANGELOG.md](CHANGELOG.md) and [IMPLEMENTATION.md](IMPLEMENTATION.md) §7.

### Run the dev loop

The whole stack runs in Docker — `postgres` + `api` (:8000) + `web` (:5180). No manual
`uvicorn` / `pnpm dev`:

```bash
docker compose up        # first run builds the api image (torch + Playwright — large)
```

Open **http://localhost:5180**. Backend source (`server/src`) and frontend source (`web/`)
are bind-mounted, so edits hot-reload in the containers. Models cache under `data/` (shared
with the host, so no re-download). Put `OPENROUTER_API_KEY` in a root `.env` (see
`.env.example`) — compose passes it into `api` for BYOK reasoning; it's never baked into the image.

On a **fresh** database, ingest the seed corpus once:

```bash
docker compose exec api uv run python -m noscia.ingest.run    # crawl seeds → embed → index
```

Phase 2 tooling (inside the api container, or `cd server` on the host):

```bash
docker compose exec api uv run python -m noscia.train.eval        # eval (nDCG@10 / MRR / Recall@10)
docker compose exec api uv run python -m noscia.ingest.run --due  # recrawl only sources past cadence
```

Fine-tuning is offline and host-only (the `train` deps aren't in the image):

```bash
cd server && uv sync --group train
uv run --group train python -m noscia.train.synth                        # BYOK synthetic pairs
uv run --group train python -m noscia.train.finetune --train --compare   # LoRA fine-tune, eval-gated
```

> Prefer running natively? The host loop still works: `docker compose up -d postgres`, then
> `cd server && uv run uvicorn noscia.app:app --reload` and `pnpm dev`.

## Stack (planned)

React + TypeScript + Vite (pnpm) · Python + FastAPI · Postgres + pgvector + `pg_search` BM25 (one datastore) · crawl4ai · Qwen3-Embedding-0.6B · bge-reranker-v2-m3 · BYOK LLM providers.
