"""Ingest runner — seeds → crawl → chunk → embed → upsert.

The one place the pipeline is composed for writes. Exposed three ways:
  * ``python -m noscia.ingest.run``  — register seeds from the YAML and index all,
  * ``ingest_specs(...)``            — awaited by the Corpus API endpoints,
  * ``register_seeds()``            — load the YAML into the `sources` table.

Each page is fully re-indexed (delete-by-url then upsert) so a re-crawl never leaves
stale chunks behind. Source status walks idle → crawling → done|error for the UI.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import yaml

from .. import corpus, db
from ..search.embed import embed_docs
from ..search.store import Chunk, get_store
from .chunk import chunk_markdown
from .crawl import crawl_many

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
    """Stable per (url, ordinal) so re-ingest updates in place."""
    return hashlib.sha256(f"{url}#{ordinal}".encode()).hexdigest()


async def ingest_specs(specs: list[dict]) -> dict:
    """Crawl + index the given seed specs ({url, source_type, org, cadence})."""
    store = get_store()
    by_url = {s["url"]: s for s in specs}
    for s in specs:
        corpus.set_status(s["url"], "crawling")

    pages = await crawl_many(list(by_url))

    indexed_pages = 0
    total_chunks = 0
    errors: list[dict] = []
    for page in pages:
        spec = by_url[page.url]
        if not page.ok:
            corpus.set_status(page.url, "error", page.error)
            errors.append({"url": page.url, "error": page.error})
            continue

        text_chunks = chunk_markdown(page.markdown)
        if not text_chunks:
            corpus.set_status(page.url, "error", "no text after chunking")
            errors.append({"url": page.url, "error": "no text after chunking"})
            continue

        vectors = embed_docs([c.text for c in text_chunks])
        records = [
            Chunk(
                id=_chunk_id(page.url, tc.ordinal),
                url=page.url,
                title=page.title,
                text=tc.text,
                source_type=spec["source_type"],
                org=spec.get("org"),
                content_hash=tc.content_hash,
                token_count=tc.token_count,
                dense=vec,
            )
            for tc, vec in zip(text_chunks, vectors, strict=True)
        ]
        store.delete_url(page.url)
        store.upsert(records)
        corpus.finish_source(page.url, pages=1, chunks=len(records))
        indexed_pages += 1
        total_chunks += len(records)

    return {
        "ok": not errors,
        "indexed_pages": indexed_pages,
        "chunks": total_chunks,
        "errors": errors,
    }


async def ingest_all() -> dict:
    seeds = register_seeds()
    return await ingest_specs(seeds)


def main() -> None:
    db.init_schema()
    seeds = register_seeds()
    print(f"Registered {len(seeds)} seeds. Crawling + indexing…")
    summary = asyncio.run(ingest_specs(seeds))
    print(
        f"Done: {summary['indexed_pages']} pages, {summary['chunks']} chunks indexed."
        + (f" {len(summary['errors'])} errors." if summary["errors"] else "")
    )
    for e in summary["errors"]:
        print(f"  ! {e['url']}: {e['error']}")


if __name__ == "__main__":
    main()
