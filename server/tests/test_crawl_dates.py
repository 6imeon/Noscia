"""Publication-date extraction from HTML head meta / JSON-LD (evidence-or-null)."""

from datetime import UTC, datetime
from types import SimpleNamespace

from noscia.ingest.crawl import (
    _parse_date,
    _published_at_from_html,
    _published_at_of,
)


def test_parse_date_iso_timestamp_and_date_only():
    assert _parse_date("2023-05-01T09:30:00Z") == datetime(2023, 5, 1, 9, 30, tzinfo=UTC)
    assert _parse_date("2023-05-01") == datetime(2023, 5, 1, tzinfo=UTC)
    # offset is normalized to UTC
    assert _parse_date("2023-05-01T12:00:00+02:00") == datetime(2023, 5, 1, 10, tzinfo=UTC)


def test_parse_date_rejects_prose_and_out_of_window():
    assert _parse_date("May 1st, 2023") is None  # not ISO → blank beats a guess
    assert _parse_date("") is None
    assert _parse_date("1970-01-01") is None  # pre-1990 sanity floor (epoch placeholder)


def test_html_article_published_time_wins():
    html = """
    <html><head>
      <meta property="og:title" content="x">
      <meta name="date" content="2024-02-02">
      <meta property="article:published_time" content="2024-01-15T08:00:00Z">
    </head><body>...</body></html>
    """
    # article:published_time outranks a bare name="date" in the priority list
    assert _published_at_from_html(html) == datetime(2024, 1, 15, 8, tzinfo=UTC)


def test_html_jsonld_datepublished_fallback():
    html = (
        '<head><script type="application/ld+json">'
        '{"datePublished": "2022-11-03"}</script></head>'
    )
    assert _published_at_from_html(html) == datetime(2022, 11, 3, tzinfo=UTC)


def test_html_no_date_is_none():
    assert _published_at_from_html("<head><title>no date here</title></head>") is None
    assert _published_at_from_html("") is None


def test_published_at_of_prefers_metadata_then_html():
    # crawl4ai metadata dict carries the date → used without scanning html
    meta_result = SimpleNamespace(
        metadata={"article:published_time": "2025-03-09"}, html="<head></head>"
    )
    assert _published_at_of(meta_result) == datetime(2025, 3, 9, tzinfo=UTC)
    # no metadata date → falls back to the raw html head
    html_result = SimpleNamespace(
        metadata={"title": "x"},
        html='<head><meta name="date" content="2021-07-07"></head>',
    )
    assert _published_at_of(html_result) == datetime(2021, 7, 7, tzinfo=UTC)
