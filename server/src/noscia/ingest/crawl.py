"""Crawling — crawl4ai (v0.8.x) → clean, LLM-ready markdown + title/metadata.

Headless Chromium (Playwright) renders each seed; crawl4ai emits pruned markdown.
One page at a time with per-URL error capture so one dead seed never sinks a run.
Run ``crawl4ai-setup`` once to install the browser (IMPLEMENTATION §3).

Phase 2 freshness adds a cheap **conditional pre-check** (``check_conditional``): a
streamed HTTP GET that echoes the stored ``ETag`` / ``Last-Modified`` back as
``If-None-Match`` / ``If-Modified-Since``. A ``304 Not Modified`` short-circuits the
whole expensive browser render. When the server doesn't honor validators we fall
through to a full crawl and the content-hash diff catches the no-op anyway.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from .url import canonical_url

# A real UA — some hosts 403 the default httpx agent (and skip validators for it).
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 Noscia/0.1 (ESG corpus crawler)"
)

# Consent-widget containers to drop before extraction (covers the major CMPs: Cookiebot,
# OneTrust, plus generic cookie banners). Removes the whole declaration table at the
# source — cleaner than scrubbing its cell text post-hoc, and unlike remove_overlay_elements
# it never touches the main content container.
_CONSENT_SELECTOR = (
    "#CybotCookiebotDialog, #onetrust-consent-sdk, #onetrust-banner-sdk, "
    ".onetrust-pc-dark-filter, #cookie-banner, #cookie-notice, .cookie-consent, "
    ".cookie-banner, [aria-label='cookieconsent'], [class*='CookieDeclaration']"
)


@dataclass
class CrawledPage:
    url: str
    title: str
    markdown: str
    ok: bool = True
    error: str | None = None
    published_at: datetime | None = None  # document publish date when found (else None)


@dataclass
class Conditional:
    """Result of the cheap validator probe before a full crawl."""

    not_modified: bool = False  # server returned 304 → skip the browser render
    etag: str | None = None  # fresh validators to persist for next time
    last_modified: str | None = None
    error: str | None = None  # probe failed → caller should fall through to crawl


async def check_conditional(
    url: str, etag: str | None, last_modified: str | None, timeout_s: float = 15.0
) -> Conditional:
    """Streamed conditional GET. 304 ⇒ not_modified; else capture fresh validators.

    Streamed so a ``200`` doesn't pull the body (the browser re-fetches anyway); a
    ``304`` carries no body. Any failure returns ``error`` set so the caller crawls
    rather than wrongly skipping a possibly-changed page.
    """
    import httpx

    headers = {"User-Agent": _UA}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_s) as client:
            req = client.build_request("GET", url, headers=headers)
            resp = await client.send(req, stream=True)
            await resp.aclose()  # headers + status only; never download the body
        if resp.status_code == 304:
            return Conditional(not_modified=True, etag=etag, last_modified=last_modified)
        return Conditional(
            not_modified=False,
            etag=resp.headers.get("ETag"),
            last_modified=resp.headers.get("Last-Modified"),
        )
    except Exception as exc:  # never let a probe failure mask a real change
        return Conditional(error=f"{type(exc).__name__}: {exc}")


def _build_run_config(page_timeout_ms: int, deep_strategy=None):
    """Shared crawl config tuned for **clean ESG content**, not page chrome.

    The defaults emit crawl4ai's *raw* markdown — which on these sites is dominated by
    cookie-consent banners, cookie-declaration tables, language menus and nav. We fix
    that at the source:
      * ``PruningContentFilter`` — density/link-ratio heuristic drops boilerplate blocks
        (cookie banners, declaration tables, menus), populating ``fit_markdown`` (the
        main-content variant ``_extract_markdown`` prefers);
      * ``excluded_tags`` — nav/header/footer/aside/form never reach the markdown;
      * links/images dropped (labels kept) so passages read as prose, not link soup.

    Note: ``remove_overlay_elements`` is deliberately **off** — on some ESG sites
    (e.g. ghgprotocol.org) it misfires, classifying the main content container as an
    overlay and deleting the page. Instead we drop the common consent-widget containers
    by CSS id/class (``_CONSENT_SELECTOR``: Cookiebot, OneTrust, generic) — GRI renders a
    full Cookiebot declaration table inline, which the density filter would otherwise keep.
    """
    from crawl4ai import CacheMode, CrawlerRunConfig, DefaultMarkdownGenerator
    from crawl4ai.content_filter_strategy import PruningContentFilter

    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(
            threshold=0.5, threshold_type="dynamic", min_word_threshold=5
        ),
        options={"ignore_links": True, "ignore_images": True, "body_width": 0},
    )
    kwargs = dict(
        cache_mode=CacheMode.BYPASS,  # always re-fetch on an explicit ingest
        page_timeout=page_timeout_ms,
        word_count_threshold=20,  # drop short boilerplate blocks
        markdown_generator=md_generator,
        excluded_tags=["nav", "header", "footer", "aside", "form"],
        excluded_selector=_CONSENT_SELECTOR,  # drop cookie/consent widgets at the source
        # NB: external links are kept in result.links (needed for allow-listed PDF-host
        # discovery, e.g. TCFD's assets.bbhub.io CDN). Markdown stays link-free via the
        # generator's ignore_links; deep-crawl scope is bounded by the BFS
        # include_external=False, so keeping them here never widens traversal.
        exclude_social_media_links=True,
    )
    if deep_strategy is not None:
        kwargs["deep_crawl_strategy"] = deep_strategy
        kwargs["stream"] = False  # collect the whole frontier, then return one list
    return CrawlerRunConfig(**kwargs)


def _extract_markdown(result) -> str:
    """crawl4ai 0.8.x: result.markdown may be a MarkdownGenerationResult or str."""
    md = getattr(result, "markdown", "") or ""
    # Prefer the noise-pruned variant when present, else the raw markdown.
    for attr in ("fit_markdown", "raw_markdown"):
        val = getattr(md, attr, None)
        if val:
            return val
    return str(md)


def _title_of(result, url: str) -> str:
    meta = getattr(result, "metadata", None) or {}
    return (meta.get("title") or "").strip() or url


# Head-meta keys that carry a document's publish date, most-authoritative first. Lowercased
# at lookup, so these match regardless of the tag's original case (DC.date.issued, etc.).
_DATE_META_KEYS = (
    "article:published_time",
    "og:published_time",
    "citation_publication_date",
    "citation_date",
    "dcterms.date",
    "dcterms.created",
    "dc.date.issued",
    "dc.date",
    "datepublished",
    "publishdate",
    "publish-date",
    "pubdate",
    "date",
)
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_JSONLD_DATE_RE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"', re.IGNORECASE)


def _parse_date(raw: str) -> datetime | None:
    """Parse a common HTML/ISO date string to a tz-aware UTC ``datetime`` (None if not).

    Handles ISO-8601 with ``Z``/offset and bare ``YYYY-MM-DD``; anything else (prose
    dates, ``DD/MM/YYYY``) falls through to None — blank beats a guessed date (rule 8).
    A sanity window rejects parser garbage (epoch 0, far-future placeholders).
    """
    s = (raw or "").strip()
    if not s:
        return None
    iso = s.replace("Z", "+00:00")
    for candidate in (iso, iso[:10]):  # full timestamp, then date-only prefix
        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        if 1990 <= dt.year <= datetime.now(UTC).year + 1:
            return dt.astimezone(UTC)
        return None
    return None


def _meta_attr(tag: str, name: str) -> str | None:
    m = re.search(rf'{name}\s*=\s*"([^"]*)"', tag, re.IGNORECASE) or re.search(
        rf"{name}\s*=\s*'([^']*)'", tag, re.IGNORECASE
    )
    return m.group(1) if m else None


def _published_at_from_html(html: str) -> datetime | None:
    """Scan a page's ``<head>`` meta tags (and JSON-LD) for a publish date."""
    if not html:
        return None
    head = html[:200_000]  # dates live in <head>; cap the scan so a huge body is cheap
    found: dict[str, str] = {}
    for tag in _META_TAG_RE.findall(head):
        key = _meta_attr(tag, "property") or _meta_attr(tag, "name") or _meta_attr(tag, "itemprop")
        content = _meta_attr(tag, "content")
        if key and content:
            found.setdefault(key.lower().strip(), content)
    for key in _DATE_META_KEYS:
        if key in found:
            dt = _parse_date(found[key])
            if dt:
                return dt
    m = _JSONLD_DATE_RE.search(head)
    return _parse_date(m.group(1)) if m else None


def _published_at_of(result) -> datetime | None:
    """Document publish date from crawl4ai metadata, else the raw HTML head (None if absent)."""
    meta = getattr(result, "metadata", None) or {}
    for k in ("article:published_time", "og:published_time", "published_time", "date"):
        val = meta.get(k)
        if val:
            dt = _parse_date(str(val))
            if dt:
                return dt
    html = getattr(result, "html", None) or getattr(result, "cleaned_html", None) or ""
    return _published_at_from_html(html)


def _registrable_domain(url: str) -> str:
    """Host minus a leading ``www.`` — the same-site test for PDF discovery."""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _collect_pdf_urls(
    results, seed_url: str, *, pdf_hosts: set[str], exclude_patterns: list[str] | None
) -> list[str]:
    """Same-site (or allow-listed) PDF links discovered across the crawled pages.

    A deep crawl can't follow a PDF (it's not HTML), but the pages it *does* render
    link to the authoritative documents. We harvest those links, keep ones on the
    seed's own domain or an operator-approved host (``pdf_hosts`` — e.g. TCFD's
    ``assets.bbhub.io`` CDN), drop anything matching the junk ``exclude_patterns``,
    and dedupe on the canonical URL. Curated, not open-web (CLAUDE.md rule 11/13).
    """
    import fnmatch

    seed_domain = _registrable_domain(seed_url)
    allowed = {h.lower() for h in pdf_hosts}
    out: list[str] = []
    seen: set[str] = set()
    for result in results or []:
        links = getattr(result, "links", None) or {}
        for entry in list(links.get("internal", [])) + list(links.get("external", [])):
            href = (entry or {}).get("href") if isinstance(entry, dict) else None
            if not href or not urlsplit(href).path.lower().endswith(".pdf"):
                continue
            host = (urlsplit(href).hostname or "").lower()
            if _registrable_domain(href) != seed_domain and host not in allowed:
                continue
            low = href.lower()
            if exclude_patterns and any(fnmatch.fnmatch(low, p.lower()) for p in exclude_patterns):
                continue
            canon = canonical_url(href)
            if canon in seen:
                continue
            seen.add(canon)
            out.append(canon)
    return out


async def crawl_site(
    seed_url: str,
    *,
    max_depth: int = 1,
    max_pages: int = 25,
    exclude_patterns: list[str] | None = None,
    max_pdfs: int = 0,
    pdf_hosts: list[str] | None = None,
    page_timeout_ms: int = 45_000,
) -> list[CrawledPage]:
    """Bounded **same-domain** deep crawl from one seed (breadth-first).

    Follows internal links to ``max_depth`` (0 = just the seed) capped at
    ``max_pages``. Stays on the seed's domain (``include_external=False``); non-HTML
    (PDFs, images, archives) is dropped by content type, and any caller
    ``exclude_patterns`` (globs, e.g. ``*/login*``, ``*?*``) are blocked — keeping the
    crawl out of search/login/query-string traps. crawl4ai's memory-adaptive
    dispatcher throttles concurrency under pressure, which matters on a 18 GB box.

    When ``max_pdfs`` > 0, up to that many **PDF documents** linked from the crawled
    pages are also extracted (``ingest.pdf``) and returned as pages — the authoritative
    substance HTML-only crawling misses. They're kept to the seed's own domain plus any
    operator-approved ``pdf_hosts`` (e.g. a publications CDN), never the open web.

    One ``CrawledPage`` per rendered page or PDF (deduped by canonical URL); per-page
    failures are flagged, never raised, so a few dead links don't sink the site.
    """
    from crawl4ai import AsyncWebCrawler, BrowserConfig
    from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
    from crawl4ai.deep_crawling.filters import (
        ContentTypeFilter,
        FilterChain,
        URLPatternFilter,
    )

    filters: list = [ContentTypeFilter(allowed_types=["text/html"])]
    if exclude_patterns:
        # reverse=True ⇒ a URL matching any pattern is *blocked*.
        filters.append(URLPatternFilter(patterns=exclude_patterns, reverse=True))

    strategy = BFSDeepCrawlStrategy(
        max_depth=max_depth,
        max_pages=max_pages,
        include_external=False,  # never leave the seed's domain
        filter_chain=FilterChain(filters),
    )
    run_cfg = _build_run_config(page_timeout_ms, deep_strategy=strategy)

    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        try:
            results = await crawler.arun(url=seed_url, config=run_cfg)
        except Exception as exc:  # whole-site failure (e.g. seed unreachable)
            err = f"{type(exc).__name__}: {exc}"
            return [CrawledPage(seed_url, seed_url, "", ok=False, error=err)]

    pages: list[CrawledPage] = []
    seen: set[str] = set()
    for result in results or []:
        url = canonical_url(getattr(result, "url", seed_url))
        if url in seen:  # BFS can re-surface a URL via multiple parents / cosmetic variants
            continue
        seen.add(url)
        if not getattr(result, "success", False):
            err = getattr(result, "error_message", "crawl failed")
            pages.append(CrawledPage(url, url, "", ok=False, error=err))
            continue
        markdown = _extract_markdown(result)
        title = _title_of(result, url)
        if not markdown.strip():
            pages.append(CrawledPage(url, title, "", ok=False, error="empty markdown"))
            continue
        pages.append(CrawledPage(url, title, markdown, published_at=_published_at_of(result)))

    if max_pdfs > 0:
        pages += await _crawl_pdfs(
            results, seed_url, max_pdfs=max_pdfs, pdf_hosts=pdf_hosts, exclude=exclude_patterns
        )
    return pages


async def _crawl_pdfs(
    results,
    seed_url: str,
    *,
    max_pdfs: int,
    pdf_hosts: list[str] | None,
    exclude: list[str] | None,
) -> list[CrawledPage]:
    """Extract up to ``max_pdfs`` discovered PDFs (sequentially — pypdf is CPU-bound)."""
    from .pdf import extract_pdf

    urls = _collect_pdf_urls(
        results, seed_url, pdf_hosts=set(pdf_hosts or ()), exclude_patterns=exclude
    )[:max_pdfs]
    return [await extract_pdf(u) for u in urls]


async def crawl_many(urls: list[str], page_timeout_ms: int = 45_000) -> list[CrawledPage]:
    """Crawl each URL; return one CrawledPage per input (failures flagged, not raised)."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig

    run_cfg = _build_run_config(page_timeout_ms)
    pages: list[CrawledPage] = []
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        for raw_url in urls:
            url = canonical_url(raw_url)
            try:
                result = await crawler.arun(url=raw_url, config=run_cfg)
                if not getattr(result, "success", False):
                    err = getattr(result, "error_message", "crawl failed")
                    pages.append(CrawledPage(url, url, "", ok=False, error=err))
                    continue
                markdown = _extract_markdown(result)
                title = _title_of(result, url)
                if not markdown.strip():
                    pages.append(CrawledPage(url, title, "", ok=False, error="empty markdown"))
                    continue
                pages.append(
                    CrawledPage(url, title, markdown, published_at=_published_at_of(result))
                )
            except Exception as exc:  # one bad seed shouldn't sink the batch
                err = f"{type(exc).__name__}: {exc}"
                pages.append(CrawledPage(url, url, "", ok=False, error=err))
    return pages
