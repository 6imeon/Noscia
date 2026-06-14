# CLAUDE.md — working conventions for Noscia

Agent + contributor working notes. Read [SPEC.md](SPEC.md) (what/why) and [IMPLEMENTATION.md](IMPLEMENTATION.md) (how/when) first. This file is the short, always-true rulebook + the pinned-versions ledger.

## What this is
A company-internal, vertical **ESG neural-search** web app: Exa-style retrieval over a curated sustainability corpus with cited passages, plus an agentic entity-search mode. Self-hosted via Docker behind the company SSO; runs locally (`uvicorn` + `pnpm dev`) for development. dev == prod (same Postgres).

## Repo shape (see SPEC §3)
- **Monorepo.** `web/` = Vite + React + TS (pnpm). `server/` = FastAPI (uv, **PyPA src-layout**, package `noscia` at `server/src/noscia/`). `corpus/` = seeds + eval. `data/` = Postgres volume + model cache (gitignored).
- Run backend: `uvicorn noscia.app:app --reload` (from `server/`, venv active). Run frontend: `pnpm dev`. Datastore: `docker compose up postgres`.

## Hard rules (never retrofit — bake in from day one)
1. **pnpm everywhere on JS; uv on Python.** Commit `pnpm-lock.yaml` and `uv.lock`. Never npm/yarn.
2. **7-day dependency release cooldown** (supply-chain defense). `pnpm-workspace.yaml` → `minimumReleaseAge: 10080`; `renovate.json` → `"minimumReleaseAge": "7 days"` across npm/PyPI/Cargo. If a brand-new version won't install at init, **pin the most recent version already >7 days old** — never disable the policy. Emergency security fix bypasses only via a reviewed `minimumReleaseAgeExclude` entry.
3. **No AI attribution in git.** Plain commit messages and PR bodies — no `Co-Authored-By: Claude`, no "Generated with Claude Code" footer.
4. **Commit identity.** Author as `6imeon <260094322+6imeon@users.noreply.github.com>`. Never the real email.
5. **HTTP contract first.** Define `noscia/contract.py` ⇄ `web/src/lib/api.ts` before implementing either side. Types must match exactly.
6. **Secrets never touch the browser, never sit in source.** Read keys from `.env` (gitignored) via `get_secret()` in `noscia/config.py` — never `os.environ` directly, never name the module `secrets.py` (shadows stdlib). Backend returns only a **masked** confirmation. Ship `.env.example`. **Never read/`cat`/print `.env` or any secret value** — confirm a key is set via the masked path (`/providers`), not by opening the file. `.env.example` (no real values) is fine.
7. **Search runs without a key.** Local embeddings + local index = offline search. Only reasoning (entity search, synth data) needs BYOK.
8. **Evidence-or-null extraction.** The entity agent never emits a field it can't cite. Blank beats hallucinated.
9. **Eval-gated model changes.** Any embedding/reranker swap is gated on nDCG@10 / MRR against `corpus/eval/esg_queries.jsonl`. Decide on the ESG corpus, not leaderboards.
10. **Swappable seams from Phase 0:** `VectorStore` (→ `PgVectorStore`), `get_secret()`, `CurrentUser` (`SoloUser` | `HeaderUser`). App code talks to these, not to raw SQL / env / a hardcoded user.
11. **Keep the corpus small and the domain narrow.** Vertical quality, not coverage. Resist "search the whole web."
12. **Changelog, not README, holds the change history.** Record what landed in `CHANGELOG.md` and update it at the **end of each phase**. README stays lean (overview + usage); it never accumulates a change narrative.

## Pinned versions (fill as deps are added — rule: pin exact, record here)
| Tool / lib | Version | Notes |
|---|---|---|
| Node | 24.14.0 | local dev |
| pnpm | 11.5.1 | native cooldown default raised to 7d |
| Python | 3.12.x (via uv) | system 3.9 unused; uv manages the interpreter |
| uv | 0.11.16 | lockfile + interpreter manager |
| Docker | 27.4.0 | Compose for Postgres |
| FastAPI | 0.136.3 | locked `--exclude-newer 2026-06-07` |
| uvicorn | 0.49.0 | `[standard]` extra |
| pydantic | 2.13.4 | + pydantic-settings 2.14.1 |
| psycopg | 3.3.4 | `[binary]`; pgvector 0.4.2 |
| sqlalchemy | 2.0.50 | engine in `db.py` |
| python-dotenv | 1.2.2 | loads `.env` in `config.py` |
| ruff / pytest | 0.15.16 / 9.0.3 | dev deps |
| Postgres (ParadeDB) | 0.24.0-pg17 | bundles pgvector + pg_search; compose `postgres` service |
| Vite / React / TS | 8.0.16 / 19.2.6 / 6.0.2 | dev port pinned to **5180** (strictPort) |
| Tailwind | 4.3.0 | v4 `@tailwindcss/vite`; tokens in `@theme` (index.css) |
| vitest | 4.1.8 | + @testing-library/react, jsdom |
| crawl4ai | 0.8.9 | Phase 1 crawler; `crawl4ai-setup` (Playwright Chromium) once |
| sentence-transformers | 5.5.1 | loads embedder + cross-encoder reranker |
| torch | 2.12.0 | pulled by sentence-transformers |
| transformers | 5.10.2 | tokenizer/model backend |
| numpy | 2.4.6 | vector math (Matryoshka truncate/renormalize) |
| tiktoken | 0.13.0 | token-accurate chunking (transitive via crawl4ai) |
| pyyaml | 6.0.3 | parses `corpus/seeds.esg.yaml` |
| Qwen3-Embedding-0.6B | — | model; 1024-dim → Matryoshka 256; eval before swapping |
| bge-reranker-v2-m3 | — | model; eval vs Qwen3-Reranker-0.6B |

Cooldown is persisted in `server/pyproject.toml` → `[tool.uv] exclude-newer = "2026-06-07T00:00:00Z"` so every `uv lock`/`sync`/`run` honors the 7-day window (not just a one-shot `--exclude-newer`). Renovate advances it behind review.

Record exact versions here as each lands (IMPLEMENTATION §2 rule 8).
