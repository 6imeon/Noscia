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

from dataclasses import dataclass

# A real UA — some hosts 403 the default httpx agent (and skip validators for it).
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 Noscia/0.1 (ESG corpus crawler)"
)


@dataclass
class CrawledPage:
    url: str
    title: str
    markdown: str
    ok: bool = True
    error: str | None = None


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


async def crawl_many(urls: list[str], page_timeout_ms: int = 45_000) -> list[CrawledPage]:
    """Crawl each URL; return one CrawledPage per input (failures flagged, not raised)."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    run_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,  # always re-fetch on an explicit ingest
        page_timeout=page_timeout_ms,
        word_count_threshold=20,  # drop boilerplate blocks
    )
    pages: list[CrawledPage] = []
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        for url in urls:
            try:
                result = await crawler.arun(url=url, config=run_cfg)
                if not getattr(result, "success", False):
                    err = getattr(result, "error_message", "crawl failed")
                    pages.append(CrawledPage(url, url, "", ok=False, error=err))
                    continue
                markdown = _extract_markdown(result)
                title = _title_of(result, url)
                if not markdown.strip():
                    pages.append(CrawledPage(url, title, "", ok=False, error="empty markdown"))
                    continue
                pages.append(CrawledPage(url, title, markdown))
            except Exception as exc:  # one bad seed shouldn't sink the batch
                err = f"{type(exc).__name__}: {exc}"
                pages.append(CrawledPage(url, url, "", ok=False, error=err))
    return pages
