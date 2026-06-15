<div align="center">

# Noscia

**Vertical neural search for the fields that matter.**

Retrieval over a curated, authoritative corpus with cited passages and an agentic
entity-search mode. No open-web crawl, no invented sources.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Node](https://img.shields.io/badge/Node-24.14-339933?logo=nodedotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Postgres](https://img.shields.io/badge/Postgres-ParadeDB-4169E1?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/license-internal-555)

</div>

Noscia is a company-internal neural-search app. It answers questions with **cited passages
from a corpus you control**, one vertical at a time (ESG, economics, healthcare, and more),
and it never reaches out to a third-party search engine. Self-hosted via Docker behind your
SSO; runs locally for development.

## Highlights

- 🔎 **Cited, not guessed.** Hybrid dense + BM25 retrieval, reranked with a cross-encoder.
  Every result carries the source passage and a link, so an answer is evidence you can open.
- 🧭 **Ten verticals, on demand.** Each is its own authoritative corpus, embedded the moment
  it is first picked. Switching is instant and nothing bleeds across fields.
- 🧱 **Index-only and private.** Search runs entirely on your own index. Queries and data
  never leave your network; only optional BYOK reasoning calls a provider.
- 🧩 **Entity search.** An agent fills a structured record from the corpus alone, leaving any
  field it cannot cite blank. Blank beats hallucinated.
- 📈 **Eval-gated.** Every embedding or reranker change is gated on nDCG@10 / MRR / Recall@10
  against a held-out query set, scored at source-domain level.

## Quick start

The whole stack runs in Docker: `postgres` + `api` (:8000) + `web` (:5180).

```bash
docker compose up        # first run builds the api image (torch + Playwright, large)
```

Open **http://localhost:5180** for the app, or **http://localhost:5180/landing** for the
marketing page. Backend (`server/src`) and frontend (`web/`) are bind-mounted, so edits
hot-reload in the containers. Models cache under `data/`. Put `OPENROUTER_API_KEY` in a root
`.env` (see `.env.example`) for BYOK reasoning; it is never baked into the image.

On a fresh database, ingest a vertical once:

```bash
docker compose exec api uv run python -m noscia.ingest.run                  # default (esg)
docker compose exec api uv run python -m noscia.ingest.run --industry economics
```

Common tooling, inside the api container:

```bash
docker compose exec api uv run python -m noscia.train.eval --industry esg   # nDCG@10 / MRR / Recall@10
docker compose exec api uv run python -m noscia.ingest.run --due            # recrawl sources past cadence
```

Fine-tuning is offline and host-only (the `train` deps are not in the image):

```bash
cd server && uv sync --group train
uv run --group train python -m noscia.train.finetune --train --compare      # LoRA, eval-gated
```

> Prefer running natively? `docker compose up -d postgres`, then
> `cd server && uv run uvicorn noscia.app:app --reload`, and `pnpm dev` in `web/`.

## Project layout

```
noscia/
├── server/   FastAPI backend (uv, PyPA src-layout, package `noscia`)
├── web/      Vite + React + TypeScript frontend (pnpm)
├── corpus/   seed lists, the industry catalog, and eval sets
├── data/     Postgres volume + model cache (gitignored)
└── design/   UI explorations
```

## Documentation

- **[SPEC.md](SPEC.md)** : what the product is and why (architecture, search pipeline,
  entity search, constraints).
- **[IMPLEMENTATION.md](IMPLEMENTATION.md)** : build plan, hard constraints, and the
  phase-by-phase checklist.
- **[CHANGELOG.md](CHANGELOG.md)** : what changed, updated at the end of each phase.
- **[CLAUDE.md](CLAUDE.md)** : working conventions and the pinned-versions ledger.

## Stack

React 19 · TypeScript · Vite (pnpm) · FastAPI (uv) · Postgres + pgvector + `pg_search` BM25
(ParadeDB) · crawl4ai · Qwen3-Embedding-0.6B · bge-reranker-v2-m3 · BYOK LLM providers.

## License

Internal. Company-internal use only; not for public distribution.
