"""Postgres connection — the only place that builds the engine.

dev == prod: the same Postgres (ParadeDB image: pgvector + pg_search) backs the
local dev loop and the company deployment (SPEC §9). ``DATABASE_URL`` selects it.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import get_secret

# Matches the docker-compose `postgres` service defaults (Step 2.5).
DEFAULT_DATABASE_URL = "postgresql+psycopg://noscia:noscia@localhost:5432/noscia"

# Canonical schema DDL (also run by fresh containers at initdb). repo-root/db/init.
_SCHEMA_SQL = Path(__file__).resolve().parents[3] / "db" / "init" / "02-schema.sql"

_engine: Engine | None = None


def database_url() -> str:
    return get_secret("database_url") or DEFAULT_DATABASE_URL


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(database_url(), pool_pre_ping=True)
    return _engine


def ping() -> bool:
    """``SELECT 1`` — True if Postgres is reachable, False otherwise."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def init_schema() -> None:
    """Apply the canonical schema (idempotent). Safe to call on every startup.

    Fresh containers run the same file at initdb; this covers the already-running
    container and keeps dev == prod from drifting.
    """
    ddl = _SCHEMA_SQL.read_text()
    with get_engine().begin() as conn:
        # psycopg can run a multi-statement script in one shot when there are no
        # bound params; the DDL is all-static, so this is safe.
        conn.exec_driver_sql(ddl)
