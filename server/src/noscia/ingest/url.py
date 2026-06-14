"""URL canonicalization — collapse near-duplicate page URLs to one citation target.

A deep crawl surfaces the *same* page under cosmetic variants: a trailing slash,
a ``#section`` fragment, a tracking query (``?utm_source=…``), or a first-page
pagination marker (``?page=1`` is byte-identical to the bare URL). Left alone these
mint distinct ``chunk_id``s (``sha256(url#ordinal)``) and surface as duplicate search
results. We fold them to one canonical form at the single point where a crawled page
gets its URL, so the diff, the prune, and the citation all key off the same string.

Conservative by design: we only drop noise that never changes the rendered content —
tracking params and the *first*-page marker. ``?page=2`` is a genuinely different page
and is preserved; any unknown query param is kept (just sorted for stability).
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query params that never affect the rendered content — analytics/click decoration.
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = frozenset(
    {"gclid", "fbclid", "mc_cid", "mc_eid", "_ga", "ref", "ref_src", "igshid", "yclid"}
)
# Pagination params whose first-page value is identical to the bare URL.
_PAGE_KEYS = frozenset({"page", "paged", "pg"})
_FIRST_PAGE = frozenset({"", "0", "1"})


def _is_noise(key: str, value: str) -> bool:
    k = key.lower()
    if k in _TRACKING_KEYS or any(k.startswith(p) for p in _TRACKING_PREFIXES):
        return True
    # page=1 / page=0 / page= → same content as no param at all; page=2+ is real.
    return k in _PAGE_KEYS and value.strip() in _FIRST_PAGE


def canonical_url(url: str) -> str:
    """Return a stable, de-duplicated form of ``url`` (see module docstring).

    Lowercases scheme+host, drops the fragment and the default port, strips a
    trailing slash (except root), removes tracking + first-page-pagination params,
    and sorts any surviving params. Non-HTTP or unparseable input is returned as-is.
    """
    if not url:
        return url
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url
    if parts.scheme not in ("http", "https"):
        return url

    host = parts.hostname or ""
    if (parts.scheme == "http" and parts.port == 80) or (
        parts.scheme == "https" and parts.port == 443
    ):
        netloc = host
    elif parts.port:
        netloc = f"{host}:{parts.port}"
    else:
        netloc = host

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode(sorted((k, v) for k, v in pairs if not _is_noise(k, v)))

    return urlunsplit((parts.scheme, netloc, path, query, ""))  # fragment dropped
