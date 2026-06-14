# Changelog

All notable changes to Noscia are recorded here. Updated at the **end of each phase**
(see [IMPLEMENTATION.md](IMPLEMENTATION.md) §7). Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); dates are absolute.

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
