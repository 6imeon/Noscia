"""Per-result answer synthesis — an Exa-style, query-focused summary (BYOK, optional).

The retriever returns the best *passage*; a passage is evidence, not an answer. When
the user opts in (and a reasoning key is configured), we ask an LLM to distill each top
result's passage into a 1–2 sentence answer to *their* query — the readable, "it
actually answers" layer on top of the cited snippet.

Grounded, never freelance (CLAUDE.md rule 8 in spirit): the model sees only the passage
and must answer from it, replying ``NONE`` when the passage doesn't address the query —
which we map to ``None`` so the UI shows the passage alone rather than a guess. BYOK via
the ``get_secret`` seam (never a raw key in source); no key ⇒ no summaries, no error.
"""

from __future__ import annotations

import asyncio
import re

from ..config import get_secret

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

# Summarizing every hit would be slow + costly; the answer lives in the top few.
DEFAULT_TOP_N = 6
_CONCURRENCY = 6
_TIMEOUT_S = 30.0
_NONE = "NONE"  # sentinel the model returns when the passage doesn't answer the query

_SYSTEM = (
    "You are an ESG research assistant. Given a user's question and a single source "
    "passage, answer the question in at most two sentences using ONLY facts stated in "
    "the passage. Do not add outside knowledge. If the passage does not actually answer "
    f"the question, reply with exactly {_NONE}."
)
_PROMPT = 'Question: {query}\n\nPassage:\n"""\n{passage}\n"""\n\nAnswer:'


def _clean(content: str) -> str | None:
    text = content.strip()
    if not text:
        return None
    # The refusal sentinel: "NONE" standing alone or trailed only by punctuation
    # ("NONE.", "NONE, the passage…"). Crucially NOT "None of the companies…", which is
    # a real answer — only a non-alphanumeric follower counts as the sentinel.
    m = re.match(r"none(\W|$)", text, re.IGNORECASE)
    if m and (m.group(1) == "" or not m.group(1).isspace()):
        return None
    return text


async def _summarize_one(client, model: str, key: str, query: str, passage: str) -> str | None:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _PROMPT.format(query=query, passage=passage[:2000])},
        ],
        "temperature": 0.2,
    }
    try:
        resp = await client.post(
            OPENROUTER_URL, headers={"Authorization": f"Bearer {key}"}, json=body
        )
        resp.raise_for_status()
        return _clean(resp.json()["choices"][0]["message"]["content"])
    except Exception:  # noqa: BLE001 — one failed summary must not sink the search
        return None


async def summarize(
    query: str, passages: list[str], *, model: str = DEFAULT_MODEL
) -> list[str | None]:
    """Query-focused answers for ``passages`` (order preserved; ``None`` where unavailable).

    Returns all ``None`` (and never raises) when no key is configured, so the caller can
    always attach the result blindly. Calls run concurrently, capped to keep latency sane.
    """
    key = get_secret("openrouter")
    if not key or not passages:
        return [None] * len(passages)

    import httpx

    sem = asyncio.Semaphore(_CONCURRENCY)

    async def work(passage: str) -> str | None:
        if not passage.strip():
            return None
        async with sem:
            return await _summarize_one(client, model, key, query, passage)

    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        return await asyncio.gather(*(work(p) for p in passages))
