"""Pure-function tests for the ingest/search building blocks (no models, no DB)."""

from noscia.ingest.chunk import CHUNK_TOKENS, chunk_markdown, content_hash
from noscia.search.highlight import highlight


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
