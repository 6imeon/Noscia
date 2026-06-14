"""Identity seam (SPEC §9.3).

``SoloUser`` in the dev loop (always "me"); ``HeaderUser`` reads the SSO identity
header at the reverse proxy in the company deployment. Saved-data code keys off
``current_user`` and never assumes a single user.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request


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
