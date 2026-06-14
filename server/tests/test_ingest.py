"""Pure-function tests for the ingest/search building blocks (no models, no DB)."""

from noscia.ingest.chunk import CHUNK_TOKENS, _strip_boilerplate, chunk_markdown, content_hash
from noscia.ingest.run import DEFAULT_EXCLUDE, DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES, _crawl_config
from noscia.search.highlight import highlight


def test_strip_boilerplate_drops_cookie_and_consent_ui():
    md = "\n".join([
        "The Scope 2 Guidance standardizes how corporations measure emissions.",
        "This website uses cookies to improve your experience.",  # cookie line
        "Maximum Storage Duration : 1 year",                      # cookie-table cell
        "Accept All Reject All",                                  # consent-UI phrase
        "GRI Standards enable any organization to report impacts.",
    ])
    out = _strip_boilerplate(md)
    assert "Scope 2 Guidance" in out and "GRI Standards enable" in out  # real content kept
    assert "cookie" not in out.lower()
    assert "Accept All" not in out
    assert "Storage Duration" not in out


def test_strip_boilerplate_keeps_fpic_consent():
    # "consent" is a real ESG term (Free, Prior and Informed Consent) — must survive
    md = "Free, Prior and Informed Consent (FPIC) protects indigenous land rights."
    assert _strip_boilerplate(md) == md


def test_crawl_config_defaults_when_block_absent():
    depth, max_pages, exclude = _crawl_config({"url": "https://x"})
    assert depth == DEFAULT_MAX_DEPTH
    assert max_pages == DEFAULT_MAX_PAGES
    assert exclude == DEFAULT_EXCLUDE  # global junk list, nothing extra


def test_crawl_config_reads_and_merges_overrides():
    spec = {"url": "https://x", "crawl": {"max_depth": 2, "max_pages": 40, "exclude": ["*/api/*"]}}
    depth, max_pages, exclude = _crawl_config(spec)
    assert (depth, max_pages) == (2, 40)
    assert "*/api/*" in exclude  # per-seed extra appended …
    assert set(DEFAULT_EXCLUDE) <= set(exclude)  # … on top of the global junk list


def test_crawl_config_depth_zero_is_single_page():
    depth, _, _ = _crawl_config({"url": "https://x", "crawl": {"max_depth": 0}})
    assert depth == 0  # single-page seed keeps the 304 short-circuit path


def test_chunking_sizes_and_hash_are_stable():
    text = "\n\n".join(f"Paragraph {i} about ESG disclosure and emissions." for i in range(200))
    chunks = chunk_markdown(text)
    assert chunks, "expected at least one chunk"
    assert all(c.token_count <= CHUNK_TOKENS for c in chunks)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    # content_hash is deterministic for identical text
    assert chunks[0].content_hash == content_hash(chunks[0].text)


def test_chunking_cleans_markdown_link_soup():
    md = "See ![logo](https://x/a.png) the [GHG Protocol](https://ghgprotocol.org) standard."
    chunks = chunk_markdown(md)
    body = chunks[0].text
    assert "https://" not in body  # bare urls + link targets stripped
    assert "GHG Protocol" in body  # link label kept
    assert "![" not in body


def test_highlight_marks_terms_and_escapes_html():
    text = "Scope 3 emissions cover the value chain. <script>alert(1)</script> matters."
    out = highlight("scope 3 emissions", text)
    assert "<mark>" in out
    assert "Scope" in out or "scope" in out
    # raw HTML from crawled content is escaped, never passed through
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_highlight_without_matches_returns_escaped_passage():
    out = highlight("unrelated query terms", "A short ESG sentence.")
    assert "<mark>" not in out
    assert out  # non-empty
