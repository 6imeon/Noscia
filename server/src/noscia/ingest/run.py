"""Ingest runner — seeds → (conditional) crawl → chunk → diff → embed → upsert.

The one place the write pipeline is composed. Exposed several ways:
  * ``python -m noscia.ingest.run``        — register seeds + index all,
  * ``python -m noscia.ingest.run --due``  — index only sources past their cadence,
  * ``ingest_specs(...)``                  — awaited by the Corpus API endpoints,
  * ``register_seeds()``                   — load the YAML into the `sources` table.

**Phase 2 incremental crawl.** Two layers of freshness keep recrawls cheap:
  1. a conditional HTTP probe (``If-None-Match`` / ``If-Modified-Since``) — a ``304``
     skips the browser render entirely; and
  2. a per-chunk ``content_hash`` diff — only changed/new chunks are re-embedded,
     vanished chunks are pruned, unchanged chunks are left untouched.

Chunk ids are position-stable (``sha256(url#ordinal)``) so the diff lands in place.
Source status walks idle → crawling → done|error for the UI.
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
from .crawl import CrawledPage, check_conditional, crawl_many

SEEDS_PATH = Path(__file__).resolve().parents[4] / "corpus" / "seeds.esg.yaml"


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


def _index_page(page: CrawledPage, spec: dict) -> PageResult:
    """Diff a freshly crawled page against the index; embed only what changed."""
    store = get_store()
    text_chunks = chunk_markdown(page.markdown)
    if not text_chunks:
        corpus.set_status(page.url, "error", "no text after chunking")
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
            title=page.title,
            text=tc.text,
            source_type=spec["source_type"],
            org=spec.get("org"),
            content_hash=tc.content_hash,
            token_count=tc.token_count,
            dense=vec,
        )
        for (cid, tc), vec in zip(changed, vectors, strict=True)
    ]
    store.upsert(records)
    vanished = [cid for cid in existing if cid not in new_ids]
    store.delete_ids(vanished)

    total = len(text_chunks)
    corpus.finish_source(page.url, pages=1, chunks=total)
    return PageResult(
        url=page.url,
        changed=len(changed),
        skipped=total - len(changed),
        removed=len(vanished),
        chunks=total,
    )


async def ingest_specs(specs: list[dict], *, conditional: bool = True) -> dict:
    """Crawl + incrementally index the given seed specs.

    With ``conditional`` (default), a cheap HTTP validator probe short-circuits
    unchanged pages with a ``304`` before the expensive browser render.
    """
    by_url = {s["url"]: s for s in specs}
    for s in specs:
        corpus.set_status(s["url"], "crawling")

    # 1. Conditional probes — concurrent, cheap; a 304 skips the render.
    not_modified = 0
    to_crawl: list[str] = list(by_url)
    fresh_validators: dict[str, tuple[str | None, str | None]] = {}
    if conditional:
        probes = await asyncio.gather(
            *(check_conditional(url, *corpus.get_validators(url)) for url in by_url)
        )
        to_crawl = []
        for url, cond in zip(by_url, probes, strict=True):
            if cond.not_modified:
                corpus.touch_unmodified(url)
                not_modified += 1
            else:
                to_crawl.append(url)
                if not cond.error:
                    fresh_validators[url] = (cond.etag, cond.last_modified)

    # 2. Full crawl + diff-index for everything that may have changed.
    pages = await crawl_many(to_crawl)
    results: list[PageResult] = []
    errors: list[dict] = []
    for page in pages:
        spec = by_url[page.url]
        if not page.ok:
            corpus.set_status(page.url, "error", page.error)
            errors.append({"url": page.url, "error": page.error})
            continue
        res = _index_page(page, spec)
        if res.error:
            errors.append({"url": res.url, "error": res.error})
            continue
        if page.url in fresh_validators:
            corpus.save_validators(page.url, *fresh_validators[page.url])
        results.append(res)

    return {
        "ok": not errors,
        "indexed_pages": len(results),
        "not_modified": not_modified,
        "chunks": sum(r.chunks for r in results),
        "changed_chunks": sum(r.changed for r in results),
        "skipped_chunks": sum(r.skipped for r in results),
        "removed_chunks": sum(r.removed for r in results),
        "errors": errors,
    }


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
