"""Identity seam (SPEC §9.3).

``SoloUser`` in the dev loop (always "me"); ``HeaderUser`` reads the SSO identity
header at the reverse proxy in the company deployment. Saved-data code keys off
``current_user`` and never assumes a single user.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import text

from . import db

# Multi-industry: the vertical a user falls back to before they've picked one.
DEFAULT_INDUSTRY = "esg"


@dataclass(frozen=True)
class User:
    id: str
    name: str
    is_admin: bool = False


# Dev loop: one user, full admin.
SOLO_USER = User(id="solo", name="Local Dev", is_admin=True)

# Reverse-proxy SSO (oauth2-proxy / Entra) sets this header; HeaderUser reads it.
SSO_USER_HEADER = "X-Auth-Request-User"


def current_user(request: Request) -> User:
    """FastAPI dependency returning the request's user.

    Today: always ``SOLO_USER``. When SSO lands, swap the body to read
    ``request.headers[SSO_USER_HEADER]`` — call sites do not change.
    """
    return SOLO_USER


def get_active_industry(user: User) -> str:
    """The user's currently-loaded vertical (MULTI_INDUSTRY.md §5.4). Falls back to
    ``DEFAULT_INDUSTRY`` before they've chosen — so the existing single-corpus flow keeps
    working with no `user_prefs` row."""
    with db.get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT active_industry FROM user_prefs WHERE user_id = :uid"),
            {"uid": user.id},
        ).first()
    return row.active_industry if row else DEFAULT_INDUSTRY


def set_active_industry(user: User, industry: str) -> None:
    """Persist the user's active vertical (upsert keyed by ``User.id``)."""
    with db.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO user_prefs (user_id, active_industry, updated_at)
                VALUES (:uid, :industry, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    active_industry = EXCLUDED.active_industry,
                    updated_at = now()
                """
            ),
            {"uid": user.id, "industry": industry},
        )
