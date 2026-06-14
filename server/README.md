# noscia (server)

Company-internal ESG neural-search backend — FastAPI, PyPA src-layout, uv-managed.

## Develop

```bash
uv sync                              # create venv, install locked deps
uv run uvicorn noscia.app:app --reload
```

Backend serves on `http://localhost:8000`. `/health` pings Postgres (`SELECT 1`);
bring the datastore up first with `docker compose up postgres` from the repo root.

## Checks

```bash
uv run ruff check .
uv run pytest
```

## Layout

`src/noscia/` — `app.py` (entrypoint), `contract.py` (HTTP contract, mirrored in
`web/src/lib/api.ts`), `config.py` (`get_secret()` — the only secret seam),
`db.py` (Postgres engine), `user.py` (`CurrentUser` seam), `search/store.py`
(`VectorStore` seam). See repo `SPEC.md` §3 / `IMPLEMENTATION.md` §4.

Dependency versions follow the 7-day release cooldown (repo `CLAUDE.md`): at
init, `uv lock --exclude-newer <date 7 days ago>`.
