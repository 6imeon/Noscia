"""Answer synthesis — one query-focused answer over the retrieved passages (BYOK).

The retriever returns the best *passages*; a passage is evidence, not an answer — and
the answer is often spread across several of them. When the user opts in (and a
reasoning key is configured) we make a *single* LLM call over the top passages and
synthesize a short, direct answer to their query, with inline ``[n]`` citations back to
the result rows it drew on. This is the readable "it actually answers" layer, in the
spirit of Exa's/Perplexity's answer — shown once, above the results, every search.

Grounded, never freelance (CLAUDE.md rule 8): the model sees only the retrieved
passages and must answer from them, replying ``NONE`` when they don't contain the
answer — which we surface honestly rather than inventing one. BYOK via the
``get_secret`` seam (never a raw key in source); no key ⇒ no answer, no error.
"""

from __future__ import annotations

import re

from ..config import get_secret

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

# The answer is drawn from this many top passages — enough to cover an answer split
# across results without ballooning the prompt (or the cost).
DEFAULT_TOP_N = 6
_TIMEOUT_S = 30.0
_NONE = "NONE"  # sentinel the model returns when the passages don't answer the query

_SYSTEM = (
    "You are an ESG research assistant. Answer the user's question in 2–4 sentences "
    "using ONLY the numbered source passages provided — no outside knowledge. Cite the "
    "sources you actually use inline as [n], matching their numbers. If the passages do "
    f"not contain the answer, reply with exactly {_NONE}."
)


def _format_sources(passages: list[str]) -> str:
    return "\n\n".join(f"[{i}] {p[:1500]}" for i, p in enumerate(passages, start=1) if p.strip())


def _parse(content: str, n: int) -> tuple[str | None, list[int]]:
    """``(answer, cited_ranks)`` from the model reply; ``(None, [])`` on the refusal sentinel."""
    text = content.strip()
    # Refusal: "NONE" alone or trailed only by punctuation — but not "None of the…".
    m = re.match(r"none(\W|$)", text, re.IGNORECASE)
    if not text or (m and (m.group(1) == "" or not m.group(1).isspace())):
        return None, []
    cited = sorted({int(x) for x in re.findall(r"\[(\d+)\]", text) if 1 <= int(x) <= n})
    return text, cited


async def synthesize_answer(
    query: str, passages: list[str], *, model: str = DEFAULT_MODEL
) -> tuple[str | None, list[int]]:
    """A single grounded answer over ``passages`` + the 1-based ranks it cites.

    Returns ``(None, [])`` (and never raises) when no key is configured or the passages
    don't answer the query, so the caller can attach the result blindly.
    """
    key = get_secret("openrouter")
    sources = _format_sources(passages)
    if not key or not sources:
        return None, []

    import httpx

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Question: {query}\n\nSources:\n{sources}\n\nAnswer:"},
        ],
        "temperature": 0.2,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(
                OPENROUTER_URL, headers={"Authorization": f"Bearer {key}"}, json=body
            )
            resp.raise_for_status()
            return _parse(resp.json()["choices"][0]["message"]["content"], len(passages))
    except Exception:  # noqa: BLE001 — a failed answer must not sink the search
        return None, []
