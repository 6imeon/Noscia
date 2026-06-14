"""Highlighting — return the best-matching passage per result, not the whole page.

Picks the highest-overlap sentence window inside a chunk and wraps the query terms
in ``<mark>…</mark>`` (the §8.2 ``--mark`` style). Crawled text is HTML-escaped
*before* marks are inserted, so a passage can never inject markup into the reader.
"""

from __future__ import annotations

import html
import re

MAX_CHARS = 360

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "be", "by", "with", "as", "at", "from", "that", "this", "it", "its", "how",
    "what", "which", "do", "does", "we", "our", "their",
}
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-']+")


def _terms(query: str) -> list[str]:
    seen: list[str] = []
    for w in _WORD.findall(query.lower()):
        if len(w) > 2 and w not in _STOP and w not in seen:
            seen.append(w)
    return seen


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _score(sentence: str, terms: list[str]) -> int:
    low = sentence.lower()
    return sum(low.count(t) for t in terms)


def highlight(query: str, text: str, max_chars: int = MAX_CHARS) -> str:
    """Best passage window for `text` against `query`, with `<mark>` term spans."""
    terms = _terms(query)
    sentences = _sentences(text)
    if not sentences:
        return _mark(html.escape(text[:max_chars]), terms)

    if terms:
        scores = [_score(s, terms) for s in sentences]
        best = max(range(len(sentences)), key=lambda i: scores[i])
        if scores[best] == 0:
            best = 0
    else:
        best = 0

    # Grow a window outward from the best sentence until we hit max_chars.
    window = [sentences[best]]
    length = len(sentences[best])
    lo = hi = best
    while length < max_chars and (lo > 0 or hi < len(sentences) - 1):
        if hi < len(sentences) - 1:
            hi += 1
            window.append(sentences[hi])
            length += len(sentences[hi]) + 1
        if length < max_chars and lo > 0:
            lo -= 1
            window.insert(0, sentences[lo])
            length += len(sentences[lo]) + 1

    passage = " ".join(window)
    if len(passage) > max_chars + 80:
        passage = passage[: max_chars + 80].rsplit(" ", 1)[0] + "…"
    return _mark(html.escape(passage), terms)


def _mark(escaped: str, terms: list[str]) -> str:
    if not terms:
        return escaped
    # Terms are alphanumeric, so HTML-escaping didn't alter them — safe to wrap now.
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.IGNORECASE
    )
    return pattern.sub(r"<mark>\1</mark>", escaped)
