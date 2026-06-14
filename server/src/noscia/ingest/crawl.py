"""Crawling — crawl4ai (v0.8.x) → clean, LLM-ready markdown + title/metadata.

Headless Chromium (Playwright) renders each seed; crawl4ai emits pruned markdown.
One page at a time with per-URL error capture so one dead seed never sinks a run.
Run ``crawl4ai-setup`` once to install the browser (IMPLEMENTATION §3).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CrawledPage:
    url: str
    title: str
    markdown: str
    ok: bool = True
    error: str | None = None


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
