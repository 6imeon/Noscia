# Noscia

A vertical, ESG-domain neural search app — Exa-style retrieval over a curated sustainability corpus, with cited passages and an agentic entity-search mode. A company-internal tool: self-hosted via Docker behind the company's SSO, one shared index. Runs locally (`uvicorn` + `pnpm dev`) for development.

## Documents

- **[SPEC.md](SPEC.md)** — what the product is and why (architecture, search pipeline, entity search, constraints).
- **[IMPLEMENTATION.md](IMPLEMENTATION.md)** — current build plan: verified stack research, hard constraints, phase-by-phase checklist, the selected frontend design (§8), and deployment targets (§9).
- **[CHANGELOG.md](CHANGELOG.md)** — what changed, updated at the end of each phase.
- **[design/mockups/](design/mockups/)** — interactive UI explorations. Selected direction: `design-1-research-console.html`.

## Status

Phase 0 (skeleton + guardrails) complete. See [CHANGELOG.md](CHANGELOG.md) for what landed and [IMPLEMENTATION.md](IMPLEMENTATION.md) §7 for the working tracker.

### Run the dev loop

```bash
docker compose up -d postgres                       # datastore (pgvector + pg_search)
cd server && uv sync && uv run uvicorn noscia.app:app --reload   # API on :8000
pnpm install && pnpm dev                             # web on :5180 (proxies /api → :8000)
```

## Stack (planned)

React + TypeScript + Vite (pnpm) · Python + FastAPI · Postgres + pgvector + `pg_search` BM25 (one datastore) · crawl4ai · Qwen3-Embedding-0.6B · bge-reranker-v2-m3 · BYOK LLM providers.
