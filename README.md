# Noscia

A vertical, ESG-domain neural search app — Exa-style retrieval over a curated sustainability corpus, with cited passages and an agentic entity-search mode. Local-first; optionally self-hosted for a single company.

## Documents

- **[SPEC.md](SPEC.md)** — what the product is and why (architecture, search pipeline, entity search, constraints).
- **[IMPLEMENTATION.md](IMPLEMENTATION.md)** — current build plan: verified stack research, hard constraints, phase-by-phase checklist, the selected frontend design (§8), and deployment targets (§9).
- **[design/mockups/](design/mockups/)** — interactive UI explorations. Selected direction: `design-1-research-console.html`.

## Status

Pre-Phase-0 — planning and design. No application code yet. See IMPLEMENTATION.md §7 for the working tracker.

## Stack (planned)

React + TypeScript + Vite (pnpm) · Python + FastAPI · LanceDB hybrid (vector + BM25) · crawl4ai · Qwen3-Embedding-0.6B · bge-reranker-v2-m3 · BYOK LLM providers.
