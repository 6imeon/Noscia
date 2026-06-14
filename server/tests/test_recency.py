"""News-weighted recency prior — boost-only, news-only, un-dated is a no-op (rule 9)."""

from datetime import UTC, datetime, timedelta

from noscia.search.recency import (
    MAX_BOOST,
    apply_recency_prior,
    recency_multiplier,
)
from noscia.search.store import Chunk, Hit

NOW = datetime(2026, 6, 14, tzinfo=UTC)


def _hit(source_type, score, published_at=None, *, cid="c"):
    return Hit(
        chunk=Chunk(
            id=cid, url=f"https://x/{cid}", title="t", text="x",
            source_type=source_type, dense=[], published_at=published_at,
        ),
        score=score,
    )


def test_non_news_is_never_adjusted():
    old = NOW - timedelta(days=3000)
    for t in ("framework", "regulator", "ratings", "report", "ngo"):
        assert recency_multiplier(t, NOW, NOW) == 1.0  # even a same-day framework
        assert recency_multiplier(t, old, NOW) == 1.0


def test_undated_news_is_a_noop():
    assert recency_multiplier("news", None, NOW) == 1.0


def test_fresh_news_gets_full_boost_old_news_decays_toward_one():
    fresh = recency_multiplier("news", NOW, NOW)
    half_life = recency_multiplier("news", NOW - timedelta(days=180), NOW)
    ancient = recency_multiplier("news", NOW - timedelta(days=4000), NOW)
    assert fresh == 1.0 + MAX_BOOST  # same-day → full boost
    assert abs(half_life - (1.0 + MAX_BOOST / 2)) < 1e-9  # one half-life → half the boost
    assert 1.0 < ancient < 1.0 + 1e-3  # decays toward, never below, 1.0


def test_boost_is_bounded_and_never_demotes():
    # A future timestamp can't exceed the cap; nothing ever drops below baseline.
    assert recency_multiplier("news", NOW + timedelta(days=5), NOW) == 1.0 + MAX_BOOST
    assert recency_multiplier("news", NOW - timedelta(days=1), NOW) >= 1.0


def test_naive_published_at_is_treated_as_utc():
    naive = datetime(2026, 6, 14)  # no tzinfo
    assert recency_multiplier("news", naive, NOW) == 1.0 + MAX_BOOST


def test_apply_recency_prior_lifts_fresh_news_above_tie():
    # Two equally-relevant hits; the fresh news one should sort first after the prior.
    stale_framework = _hit("framework", 0.50, cid="fw")
    fresh_news = _hit("news", 0.50, published_at=NOW, cid="nw")
    ordered = apply_recency_prior([stale_framework, fresh_news], now=NOW)
    assert [h.chunk.id for h in ordered] == ["nw", "fw"]


def test_apply_recency_prior_cannot_override_a_clear_relevance_gap():
    strong_framework = _hit("framework", 0.90, cid="fw")
    fresh_news = _hit("news", 0.50, published_at=NOW, cid="nw")
    ordered = apply_recency_prior([strong_framework, fresh_news], now=NOW)
    assert ordered[0].chunk.id == "fw"  # +15% on 0.50 = 0.575 < 0.90


def test_apply_recency_prior_empty_is_empty():
    assert apply_recency_prior([]) == []
