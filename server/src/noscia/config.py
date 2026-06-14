"""Configuration + secret access — the single seam for env/secret reads.

App code calls ``get_secret("openrouter")``; it never touches ``os.environ``
directly, so a later swap to per-user keys / Vault changes this file alone
(SPEC §2 rule 4, §9.3).

NOT named ``secrets.py`` — that would shadow the Python stdlib ``secrets`` module.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Repo-root .env (gitignored; never committed). config.py lives at
# server/src/noscia/config.py → parents[3] is the repo root.
_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_ENV_PATH)

# Logical secret name → environment variable. Add new secrets here, not in callers.
_SECRET_ENV = {
    "openrouter": "OPENROUTER_API_KEY",
    "database_url": "DATABASE_URL",
}


def get_secret(name: str) -> str | None:
    """Return the secret for a logical name, or ``None`` if unset.

    The only supported way for app code to read a key. Falls back to the
    upper-cased name as the env var if it is not in the registry.
    """
    env_var = _SECRET_ENV.get(name, name.upper())
    return os.environ.get(env_var) or None


def mask(value: str | None) -> str:
    """Mask a secret for safe display — the browser never sees a raw key."""
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"
