"""Ingest runner — seeds → (conditional) crawl → chunk → diff → embed → upsert.

The one place the write pipeline is composed. Exposed several ways:
  * ``python -m noscia.ingest.run``        — register seeds + index all,
  * ``python -m noscia.ingest.run --due``  — index only sources past their cadence,
  * ``ingest_specs(...)``                  — awaited by the Corpus API endpoints,
  * ``register_seeds()``                   — load the YAML into the `sources` table.

**Phase 2.5 deep crawl.** A seed is no longer one page — it's a *site section*. Each
seed runs a bounded, same-domain BFS (``crawl_site``: ``max_depth`` / ``max_pages``
from its ``crawl:`` block) so an authoritative domain contributes its real sub-pages,
not just a landing page. Every chunk records the page it came from (``url``, the
citation target) and the seed it was discovered under (``source_url``).

**Incremental freshness** keeps recrawls cheap on three levels:
  1. single-page seeds (``max_depth: 0``) keep the conditional HTTP probe
     (``If-None-Match`` / ``If-Modified-Since``) — a ``304`` skips the render. Deep
     seeds always crawl (a landing-page ``304`` says nothing about sub-pages);
  2. a per-chunk ``content_hash`` diff — only changed/new chunks are re-embedded; and
  3. a per-seed page prune — chunks under a seed whose page has vanished are dropped.

Chunk ids are position-stable (``sha256(url#ordinal)``) so the diff lands in place.
Source status walks idle → crawling → done|error for the UI; counts roll up per seed.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from .. import corpus, db
from ..search.embed import embed_docs
from ..search.store import Chunk, get_store
from .chunk import chunk_markdown
from .crawl import CrawledPage, check_conditional, crawl_many, crawl_site

SEEDS_PATH = Path(__file__).resolve().parents[4] / "corpus" / "seeds.esg.yaml"

# Deep-crawl defaults (per-seed `crawl:` block in the YAML overrides these).
DEFAULT_MAX_DEPTH = 1  # 0 = single page (just the seed)
DEFAULT_MAX_PAGES = 25
# Same-site PDFs linked from a deep crawl are extracted too (authoritative substance
# that HTML-only crawling misses). Default a few per seed; a seed's `crawl:` block can
# raise it and allow-list an external document host (`pdf_hosts`, e.g. a publications CDN).
DEFAULT_MAX_PDFS = 4

# Junk paths every deep crawl skips (login/search/taxonomy/legal pages and feeds) —
# they carry no ESG substance and invite crawler traps. Globs; reverse-matched.
DEFAULT_EXCLUDE = [
    "*/login*", "*/signin*", "*/sign-in*", "*/search*", "*/account*",
    "*/tag/*", "*/tags/*", "*/category/*", "*/author/*",
    "*/feed*", "*/cart*", "*/privacy*", "*/cookie*", "*/terms*",
    # low-value nav/marketing pages — no ESG substance
    "*/contact*", "*/careers*", "*/jobs*", "*/join-our-team*",
    "*/donate*", "*/subscribe*", "*/newsletter*",
]


def load_seeds() -> list[dict]:
    data = yaml.safe_load(SEEDS_PATH.read_text()) or {}
    seeds = data.get("seeds", [])
    for s in seeds:
        s.setdefault("org", None)
        s.setdefault("cadence", "monthly")
    return seeds


def register_seeds() -> list[dict]:
    """Load the YAML into the `sources` table (idempotent). Returns the seeds."""
    seeds = load_seeds()
    for s in seeds:
        corpus.upsert_source(s["url"], s["source_type"], s.get("org"), s.get("cadence", "monthly"))
    return seeds


def _chunk_id(url: str, ordinal: int) -> str:
    """Stable per (url, ordinal) so re-ingest diffs in place by content_hash."""
    return hashlib.sha256(f"{url}#{ordinal}".encode()).hexdigest()


@dataclass
class PageResult:
    url: str
    changed: int = 0  # chunks re-embedded (new or content changed)
    skipped: int = 0  # chunks left untouched (content_hash matched)
    removed: int = 0  # chunks pruned (page shrank)
    chunks: int = 0  # total chunks now indexed for the page
    error: str | None = None


def _index_page(page: CrawledPage, spec: dict, source_url: str) -> PageResult:
    """Diff one crawled page against the index; embed only what changed.

    Page-scoped: upserts changed/new chunks, prunes chunks that vanished *within* the
    page. Source status/counts are owned by the seed orchestrator (``_ingest_seed``),
    not here — one seed now fans out to many pages.
    """
    store = get_store()
    text_chunks = chunk_markdown(page.markdown)
    if not text_chunks:
        return PageResult(url=page.url, error="no text after chunking")

    existing = store.existing_hashes(page.url)  # {chunk_id: content_hash}
    new_ids: set[str] = set()
    changed: list[tuple[str, object]] = []  # (id, TextChunk) needing an embed
    for tc in text_chunks:
        cid = _chunk_id(page.url, tc.ordinal)
        new_ids.add(cid)
        if existing.get(cid) != tc.content_hash:
            changed.append((cid, tc))

    vectors = embed_docs([tc.text for _, tc in changed]) if changed else []
    records = [
        Chunk(
            id=cid,
            url=page.url,
            source_url=source_url,
            title=page.title,
            text=tc.text,
            source_type=spec["source_type"],
            org=spec.get("org"),
            content_hash=tc.content_hash,
            token_count=tc.token_count,
            dense=vec,
            published_at=page.published_at,
        )
        for (cid, tc), vec in zip(changed, vectors, strict=True)
    ]
    store.upsert(records)
    vanished = [cid for cid in existing if cid not in new_ids]
    store.delete_ids(vanished)
    # Publication date is page-level: stamp every chunk of the page (including those the
    # content-hash diff left untouched) so an incremental recrawl backfills the date too.
    if page.published_at is not None:
        store.stamp_published_at(page.url, page.published_at)

    total = len(text_chunks)
    return PageResult(
        url=page.url,
        changed=len(changed),
        skipped=total - len(changed),
        removed=len(vanished),
        chunks=total,
    )


@dataclass
class CrawlConfig:
    depth: int
    max_pages: int
    exclude: list[str]
    max_pdfs: int
    pdf_hosts: list[str]


def _crawl_config(spec: dict) -> CrawlConfig:
    """Read a seed's ``crawl:`` block → depth / page+pdf caps / exclude + pdf hosts."""
    crawl = spec.get("crawl") or {}
    return CrawlConfig(
        depth=int(crawl.get("max_depth", DEFAULT_MAX_DEPTH)),
        max_pages=int(crawl.get("max_pages", DEFAULT_MAX_PAGES)),
        exclude=DEFAULT_EXCLUDE + list(crawl.get("exclude") or []),
        max_pdfs=int(crawl.get("max_pdfs", DEFAULT_MAX_PDFS)),
        pdf_hosts=list(crawl.get("pdf_hosts") or []),
    )


async def _ingest_seed(spec: dict, *, conditional: bool) -> dict:
    """Crawl + incrementally index one seed (single page or bounded deep crawl)."""
    seed = spec["url"]
    cfg = _crawl_config(spec)
    corpus.set_status(seed, "crawling")

    # Single-page seeds keep the cheap 304 short-circuit. Deep seeds always crawl —
    # a landing-page 304 says nothing about its sub-pages — and lean on the hash diff.
    fresh_validator: tuple[str | None, str | None] | None = None
    if cfg.depth <= 0:
        if conditional:
            cond = await check_conditional(seed, *corpus.get_validators(seed))
            if cond.not_modified:
                corpus.touch_unmodified(seed)
                return {"not_modified": 1}
            if not cond.error:
                fresh_validator = (cond.etag, cond.last_modified)
        pages = await crawl_many([seed])
    else:
        pages = await crawl_site(
            seed,
            max_depth=cfg.depth,
            max_pages=cfg.max_pages,
            exclude_patterns=cfg.exclude,
            max_pdfs=cfg.max_pdfs,
            pdf_hosts=cfg.pdf_hosts,
        )

    ok_pages = [p for p in pages if p.ok]
    errors: list[dict] = [{"url": p.url, "error": p.error} for p in pages if not p.ok]

    if not ok_pages:  # whole seed failed — leave the existing index untouched
        msg = errors[0]["error"] if errors else "no pages crawled"
        corpus.set_status(seed, "error", msg)
        return {"errors": errors or [{"url": seed, "error": msg}]}

    results = [_index_page(p, spec, seed) for p in ok_pages]
    errors += [{"url": r.url, "error": r.error} for r in results if r.error]
    indexed = [r for r in results if not r.error]

    # Source-level page prune: chunks under this seed whose page is gone from the site.
    removed_pages = get_store().prune_pages(seed, [r.url for r in indexed])

    chunks = sum(r.chunks for r in indexed)
    corpus.finish_source(seed, pages=len(indexed), chunks=chunks)
    if fresh_validator is not None:
        corpus.save_validators(seed, *fresh_validator)

    return {
        "indexed_pages": len(indexed),
        "chunks": chunks,
        "changed_chunks": sum(r.changed for r in indexed),
        "skipped_chunks": sum(r.skipped for r in indexed),
        "removed_chunks": sum(r.removed for r in indexed) + removed_pages,
        "errors": errors,
    }


async def ingest_specs(specs: list[dict], *, conditional: bool = True) -> dict:
    """Crawl + incrementally index each seed spec, one seed at a time.

    Seeds run sequentially (each deep crawl is already internally concurrent and
    memory-adaptive — running several browsers at once would blow the 18 GB box).
    ``conditional`` enables the 304 short-circuit for single-page seeds.
    """
    agg = {
        "indexed_pages": 0,
        "not_modified": 0,
        "chunks": 0,
        "changed_chunks": 0,
        "skipped_chunks": 0,
        "removed_chunks": 0,
        "errors": [],
    }
    for spec in specs:
        res = await _ingest_seed(spec, conditional=conditional)
        for key in (
            "indexed_pages",
            "not_modified",
            "chunks",
            "changed_chunks",
            "skipped_chunks",
            "removed_chunks",
        ):
            agg[key] += res.get(key, 0)
        agg["errors"].extend(res.get("errors", []))
    agg["ok"] = not agg["errors"]
    return agg


async def ingest_all(*, conditional: bool = True) -> dict:
    seeds = register_seeds()
    return await ingest_specs(seeds, conditional=conditional)


async def ingest_due() -> dict:
    """Recrawl only sources whose cadence window has elapsed (SPEC §7 adaptive cadence)."""
    register_seeds()
    due = corpus.sources_due()
    if not due:
        return {"ok": True, "due": 0, "indexed_pages": 0, "chunks": 0, "errors": []}
    summary = await ingest_specs(due)
    summary["due"] = len(due)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Crawl ESG seeds and (incrementally) index them.")
    ap.add_argument("--due", action="store_true", help="only sources past their cadence window")
    ap.add_argument("--full", action="store_true", help="force re-crawl (skip the 304 probe)")
    args = ap.parse_args()

    db.init_schema()
    if args.due:
        register_seeds()
        due = corpus.sources_due()
        print(f"{len(due)} source(s) due. Crawling + indexing…")
        summary = asyncio.run(ingest_due())
    else:
        seeds = register_seeds()
        print(f"Registered {len(seeds)} seeds. Crawling + indexing…")
        summary = asyncio.run(ingest_specs(seeds, conditional=not args.full))

    print(
        f"Done: {summary['indexed_pages']} pages indexed"
        f" ({summary.get('changed_chunks', 0)} chunks changed,"
        f" {summary.get('skipped_chunks', 0)} unchanged,"
        f" {summary.get('removed_chunks', 0)} pruned),"
        f" {summary.get('not_modified', 0)} unchanged via 304."
        + (f" {len(summary['errors'])} errors." if summary["errors"] else "")
    )
    for e in summary["errors"]:
        print(f"  ! {e['url']}: {e['error']}")


if __name__ == "__main__":
    main()
