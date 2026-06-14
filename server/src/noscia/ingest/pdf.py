"""PDF extraction — pull text from a PDF URL into a ``CrawledPage``.

Authoritative ESG substance often lives in PDFs, not HTML (TCFD's recommendations
and status reports, EFRAG/GRI guidance, SBTi criteria). The deep crawl drops non-HTML
by content type, so those documents never reached the index — a thin, HTML-only view
of a domain. This module fetches a PDF over HTTP (``httpx``, the validator probe's
client) and extracts its text with ``pypdf``, returning the same ``CrawledPage`` the
HTML crawler emits — so a PDF flows through the identical chunk → embed → upsert path
and cites its own URL.

No browser: PDFs are bytes, not a rendered DOM. We cap the download size (a stray
500 MB report shouldn't hang an 18 GB box) and fail soft — a bad PDF is one flagged
page, never a raised exception that sinks the seed.
"""

from __future__ import annotations

import io

from .crawl import _UA, CrawledPage

# Don't pull more than this — protects the box from an accidental huge file. ESG
# reports are typically <10 MB; 40 MB is generous headroom without being a liability.
_MAX_PDF_BYTES = 40 * 1024 * 1024
_PDF_TIMEOUT_S = 60.0


def _filename_title(url: str) -> str:
    """Human-ish title from the PDF filename when the document carries no metadata."""
    from urllib.parse import unquote, urlsplit

    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    return name.replace("-", " ").replace("_", " ").strip() or url


def _extract_text(data: bytes) -> tuple[str, str | None]:
    """``(text, pdf_title)`` from PDF bytes via pypdf. Page text joined by blank lines."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
    except (PdfReadError, OSError, ValueError) as exc:
        raise ValueError(f"unreadable PDF: {type(exc).__name__}") from exc

    if reader.is_encrypted:
        # Try the empty-password unlock some publishers use; bail if it won't open.
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001 — pypdf raises assorted crypto errors
            raise ValueError(f"encrypted PDF: {type(exc).__name__}") from exc

    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 — one bad page shouldn't drop the document
            continue
    meta = reader.metadata or {}
    pdf_title = (getattr(meta, "title", None) or "").strip() or None
    return "\n\n".join(p.strip() for p in pages if p.strip()), pdf_title


async def extract_pdf(url: str, *, max_bytes: int = _MAX_PDF_BYTES) -> CrawledPage:
    """Fetch ``url`` and extract its text into a ``CrawledPage`` (failures flagged).

    Streams the body so an oversized file is abandoned mid-download rather than buffered
    whole. A non-PDF content type, an over-cap size, an empty/scanned (image-only) PDF,
    or a parse error all return ``ok=False`` with a reason — never raise.
    """
    import httpx

    headers = {"User-Agent": _UA, "Accept": "application/pdf,*/*"}
    try:
        async with (
            httpx.AsyncClient(follow_redirects=True, timeout=_PDF_TIMEOUT_S) as client,
            client.stream("GET", url, headers=headers) as resp,
        ):
            resp.raise_for_status()
            ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ctype and "pdf" not in ctype and "octet-stream" not in ctype:
                return CrawledPage(url, url, "", ok=False, error=f"not a pdf ({ctype})")
            buf = bytearray()
            async for chunk in resp.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    return CrawledPage(
                        url, url, "", ok=False, error=f"pdf over {max_bytes} bytes"
                    )
    except Exception as exc:  # noqa: BLE001 — network/HTTP failures are per-page, not fatal
        return CrawledPage(url, url, "", ok=False, error=f"{type(exc).__name__}: {exc}")

    try:
        text, pdf_title = _extract_text(bytes(buf))
    except ValueError as exc:
        return CrawledPage(url, url, "", ok=False, error=str(exc))

    if not text.strip():
        # Likely a scanned/image-only PDF — no text layer to embed (we don't OCR).
        return CrawledPage(url, url, "", ok=False, error="empty pdf text (scanned?)")

    return CrawledPage(url, pdf_title or _filename_title(url), text)
