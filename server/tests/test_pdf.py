"""PDF discovery + title heuristics (no network — extraction is exercised live)."""

from datetime import UTC, datetime
from types import SimpleNamespace

from noscia.ingest.crawl import _collect_pdf_urls
from noscia.ingest.pdf import _clean_pdf_text, _filename_title, _pdf_published_at


def _result(*hrefs, kind="internal"):
    return SimpleNamespace(links={kind: [{"href": h} for h in hrefs]})


def test_filename_title_humanizes_when_no_metadata():
    url = "https://assets.bbhub.io/company/sites/60/2021/10/FINAL-2017-TCFD-Report.pdf"
    assert _filename_title(url) == "FINAL 2017 TCFD Report"


def test_clean_pdf_text_reflows_wraps_keeps_paragraphs():
    raw = (
        "The Task Force on Climate-\nrelated Financial\nDisclosures recommends"
        "\n\nFour core elements:"
    )
    out = _clean_pdf_text(raw)
    # hyphenated wrap rejoined (hyphen kept), lone newlines became spaces…
    assert "Climate-related Financial Disclosures recommends" in out
    # …but the blank-line paragraph break survives
    assert "recommends\n\nFour core elements:" in out
    assert "  " not in out  # no double spaces left behind


def test_clean_pdf_text_empty_is_empty():
    assert _clean_pdf_text("   \n  \n ") == ""


def test_pdf_published_at_prefers_creation_date():
    meta = SimpleNamespace(
        creation_date=datetime(2017, 6, 29, tzinfo=UTC),
        modification_date=datetime(2021, 10, 1, tzinfo=UTC),
    )
    assert _pdf_published_at(meta) == datetime(2017, 6, 29, tzinfo=UTC)


def test_pdf_published_at_falls_back_to_modification_date():
    meta = SimpleNamespace(creation_date=None, modification_date=datetime(2020, 3, 1))
    out = _pdf_published_at(meta)
    assert out == datetime(2020, 3, 1, tzinfo=UTC)  # naive normalized to UTC


def test_pdf_published_at_rejects_garbage_and_missing():
    assert _pdf_published_at(SimpleNamespace()) is None  # no date attrs at all
    assert _pdf_published_at(SimpleNamespace(creation_date=datetime(1, 1, 1))) is None  # pre-1990


def test_pdf_published_at_survives_malformed_metadata():
    class Bad:
        @property
        def creation_date(self):
            raise ValueError("malformed /CreationDate")

        modification_date = None

    assert _pdf_published_at(Bad()) is None


def test_collect_same_site_pdfs_only_by_default():
    res = [_result(
        "https://gri.org/docs/standard.pdf",      # same site → kept
        "https://gri.org/page",                    # not a pdf → skipped
        "https://cdn.elsewhere.com/x.pdf",         # other host, not allow-listed → skipped
    )]
    out = _collect_pdf_urls(
        res, "https://www.gri.org/standards", pdf_hosts=set(), exclude_patterns=None
    )
    assert out == ["https://gri.org/docs/standard.pdf"]


def test_collect_allows_listed_external_host():
    res = [_result("https://assets.bbhub.io/sites/60/FINAL-2017-TCFD-Report.pdf", kind="external")]
    out = _collect_pdf_urls(
        res, "https://www.fsb-tcfd.org/recommendations/",
        pdf_hosts={"assets.bbhub.io"}, exclude_patterns=None,
    )
    assert out == ["https://assets.bbhub.io/sites/60/FINAL-2017-TCFD-Report.pdf"]


def test_collect_applies_exclude_case_insensitively_and_dedupes():
    res = [_result(
        "https://x.org/Report-Spanish-Translation.pdf",  # excluded (case-insensitive)
        "https://x.org/report.pdf",
        "https://x.org/report.pdf",                       # dup → folded
    )]
    out = _collect_pdf_urls(
        res, "https://x.org/pubs", pdf_hosts=set(), exclude_patterns=["*spanish*"]
    )
    assert out == ["https://x.org/report.pdf"]
