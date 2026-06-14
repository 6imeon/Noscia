"""Synthetic query generation — BYOK LLM writes the queries a passage answers.

Phase 2a step 1 (SPEC §7). For each indexed chunk we ask an LLM (OpenRouter, BYOK
via the ``get_secret`` seam — never a raw key in source) for a handful of realistic
ESG search queries that the passage answers. Those ``(query, positive_passage)``
pairs train the embedder in ``finetune.py``; the held-out ``esg_queries.jsonl`` set
stays untouched so the eval never sees its own training signal.

Output: ``data/train/synth_pairs.jsonl`` (gitignored — regenerable, BYOK-derived).

    uv run python -m noscia.train.synth --per-chunk 3
    uv run python -m noscia.train.synth --model openai/gpt-4o-mini --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from .. import db
from ..config import get_secret

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
OUT_PATH = Path(__file__).resolve().parents[4] / "data" / "train" / "synth_pairs.jsonl"

_SYSTEM = (
    "You write realistic search queries for an ESG / corporate-sustainability "
    "research tool. Given a passage, output the natural-language questions a "
    "professional would type that this specific passage answers."
)

_PROMPT = (
    "Passage:\n\"\"\"\n{text}\n\"\"\"\n\n"
    "Write {n} diverse search queries this passage answers — specific, varied in "
    "phrasing (some keyword-style, some full questions), no yes/no questions. "
    'Reply ONLY with a JSON array of strings, e.g. ["query one", "query two"].'
)


@dataclass
class Chunk:
    id: str
    url: str
    text: str


def fetch_chunks(limit: int | None = None) -> list[Chunk]:
    sql = "SELECT id, url, text FROM chunks ORDER BY url, id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with db.get_engine().connect() as conn:
        rows = conn.execute(text(sql)).all()
    return [Chunk(id=r.id, url=r.url, text=r.text) for r in rows]


def _parse_queries(content: str) -> list[str]:
    """Extract a JSON array of strings, tolerating ```json fences / stray prose."""
    s = content.strip()
    start, end = s.find("["), s.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        arr = json.loads(s[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [q.strip() for q in arr if isinstance(q, str) and q.strip()]


async def _gen_for(client, model: str, key: str, chunk: Chunk, n: int) -> list[str]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _PROMPT.format(text=chunk.text[:4000], n=n)},
        ],
        "temperature": 0.7,
    }
    resp = await client.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {key}"},
        json=body,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _parse_queries(content)


async def generate(
    per_chunk: int = 3,
    model: str = DEFAULT_MODEL,
    limit: int | None = None,
    concurrency: int = 5,
    out: Path = OUT_PATH,
) -> int:
    import httpx

    key = get_secret("openrouter")
    if not key:
        raise SystemExit("No OpenRouter key configured (OPENROUTER_API_KEY). See Settings · BYOK.")

    chunks = fetch_chunks(limit)
    if not chunks:
        raise SystemExit("No indexed chunks — run `python -m noscia.ingest.run` first.")

    sem = asyncio.Semaphore(concurrency)
    pairs: list[dict] = []

    async with httpx.AsyncClient(timeout=60.0) as client:

        async def work(chunk: Chunk) -> None:
            async with sem:
                try:
                    queries = await _gen_for(client, model, key, chunk, per_chunk)
                except Exception as exc:  # one bad call shouldn't sink the run
                    print(f"  ! {chunk.id[:8]} {type(exc).__name__}: {exc}")
                    return
                for q in queries:
                    pairs.append({"query": q, "chunk_id": chunk.id, "url": chunk.url,
                                  "positive": chunk.text})

        await asyncio.gather(*(work(c) for c in chunks))

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for p in pairs:
            f.write(json.dumps(p) + "\n")
    return len(pairs)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic (query, passage) training pairs.")
    ap.add_argument("--per-chunk", type=int, default=3)
    ap.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model slug")
    ap.add_argument("--limit", type=int, default=None, help="cap chunks (smoke test)")
    args = ap.parse_args()

    print(f"Generating ~{args.per_chunk} queries/chunk via {args.model}…")
    n = asyncio.run(generate(per_chunk=args.per_chunk, model=args.model, limit=args.limit))
    print(f"Wrote {n} pairs → {OUT_PATH.relative_to(OUT_PATH.parents[2])}")


if __name__ == "__main__":
    main()
