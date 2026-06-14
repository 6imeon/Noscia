"""News-weighted recency prior (CLAUDE.md rule 9 — eval-gated).

Relevance ranks the corpus; this only *nudges* time-sensitive results so a fresher item
edges out a stale one of comparable relevance. It is deliberately narrow so it can't
hurt the evergreen core of the corpus:

  * **news-only.** Only the ``news`` source_type is eligible. Frameworks/standards are
    evergreen — TCFD's 2017 recommendations are still canonical — and must never be
    demoted for age. Every other type passes through untouched (multiplier 1.0).
  * **boost-only.** A recent item is lifted; an old one is never pushed *below* its
    relevance baseline. The multiplier is always ≥ 1.0, so the prior can break ties and
    order same-topic news, but a clear relevance gap still wins.
  * **bounded + decaying.** Capped at ``MAX_BOOST`` and decaying with a half-life, so a
    fresh news item gets at most a small edge that fades smoothly with age.
  * **un-dated = no-op.** A chunk with no extracted ``published_at`` gets multiplier 1.0
    (evidence-or-null, rule 8): a missing date never penalizes.

Applied once, after retrieval/rerank, in ``pipeline.run_search`` — and mirrored in the
eval retrievers so the gate measures exactly what ships.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .store import Hit

# Only these source types are time-sensitive enough to want a recency prior. Kept a set
# so widening it later (e.g. to "report") is a one-line, eval-gated change.
RECENCY_TYPES = frozenset({"news"})
HALF_LIFE_DAYS = 180.0  # boost halves every ~6 months of age
# Eval-tuned ceiling (rule 9). The ESG eval set holds at parity through 0.08 and regresses
# at 0.10 — at ~0.09 a fresh esgtoday piece on the SBTi net-zero standard leapfrogs SBTi's
# own authoritative page (q10). 0.05 keeps a safe margin below that cliff: the multiplier
# tops out at 1.05, so recency can only reorder items already within 5% relevance — a genuine
# tie-break, never an override of a clear winner.
MAX_BOOST = 0.05


def recency_multiplier(
    source_type: str, published_at: datetime | None, now: datetime
) -> float:
    """Score multiplier in ``[1.0, 1 + MAX_BOOST]`` — 1.0 unless this is dated news.

    Fresh news → ``1 + MAX_BOOST``; the boost decays by half every ``HALF_LIFE_DAYS`` and
    asymptotes back to 1.0 for old news (never below — boost-only).
    """
    if source_type not in RECENCY_TYPES or published_at is None:
        return 1.0
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    age_days = (now - published_at).total_seconds() / 86_400.0
    decay = 1.0 if age_days <= 0.0 else 0.5 ** (age_days / HALF_LIFE_DAYS)
    return 1.0 + MAX_BOOST * decay


def apply_recency_prior(hits: list[Hit], *, now: datetime | None = None) -> list[Hit]:
    """Re-score and re-sort ``hits`` by the news-weighted recency prior (stable for ties)."""
    if not hits:
        return hits
    now = now or datetime.now(UTC)
    adjusted = [
        Hit(
            chunk=h.chunk,
            score=h.score * recency_multiplier(h.chunk.source_type, h.chunk.published_at, now),
        )
        for h in hits
    ]
    adjusted.sort(key=lambda h: h.score, reverse=True)
    return adjusted
