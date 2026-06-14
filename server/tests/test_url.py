"""Canonical-URL folding — collapse the near-duplicate variants a crawl surfaces."""

from noscia.ingest.url import canonical_url


def test_trailing_slash_and_fragment_and_case_collapse():
    base = canonical_url("https://Example.ORG/a/b")
    assert canonical_url("https://example.org/a/b/") == base
    assert canonical_url("https://example.org/a/b#section") == base
    assert canonical_url("https://EXAMPLE.org/a/b/#x") == base


def test_first_page_marker_folds_but_later_pages_dont():
    bare = canonical_url("https://x.org/news")
    assert canonical_url("https://x.org/news?page=1") == bare  # page 1 == default
    assert canonical_url("https://x.org/news?page=0") == bare
    assert canonical_url("https://x.org/news?page=2") != bare  # real second page survives
    assert "page=2" in canonical_url("https://x.org/news?page=2")


def test_tracking_params_dropped_real_params_kept_and_sorted():
    assert canonical_url("https://x.org/a?utm_source=z&fbclid=q") == "https://x.org/a"
    # a meaningful param survives; surviving params are order-stable
    assert canonical_url("https://x.org/a?b=2&a=1") == canonical_url("https://x.org/a?a=1&b=2")
    assert "id=7" in canonical_url("https://x.org/a?id=7&utm_medium=email")


def test_root_slash_and_non_http_preserved():
    assert canonical_url("https://x.org/") == "https://x.org/"  # root slash kept
    assert canonical_url("mailto:z@x.org") == "mailto:z@x.org"  # non-http untouched
    assert canonical_url("") == ""
