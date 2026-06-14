"""Postgres connection — the only place that builds the engine.

dev == prod: the same Postgres (ParadeDB image: pgvector + pg_search) backs the
local dev loop and the company deployment (SPEC §9). ``DATABASE_URL`` selects it.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import get_secret

# Matches the docker-compose `postgres` service defaults (Step 2.5).
DEFAULT_DATABASE_URL = "postgresql+psycopg://noscia:noscia@localhost:5432/noscia"

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
