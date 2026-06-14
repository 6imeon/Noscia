"""Chunking — split a page's markdown into ~512-token passages with ~64 overlap.

Token-accurate via ``tiktoken`` (cl100k_base — a generic BPE, used only for *sizing*;
the embedder has its own tokenizer). A sliding token window keeps chunks uniform;
``highlight.py`` later picks the best sentence inside the returned chunk, so rough
window edges don't hurt result quality. Each chunk carries a ``content_hash`` so
Phase 2's incremental crawl can re-embed only what actually changed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache

CHUNK_TOKENS = 512
OVERLAP_TOKENS = 64


@dataclass
class TextChunk:
    ordinal: int  # position within the source page
    text: str
    token_count: int
    content_hash: str


@lru_cache(maxsize=1)
def _enc():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BARE_URL = re.compile(r"https?://\S+")
_MD_DECOR = re.compile(r"^[\s>*\-#=_|`]+$", re.MULTILINE)

# Consent-banner / window-chrome boilerplate that survives the content filter on some
# ESG sites (ghgprotocol, globalreporting's embedded Cookiebot declaration). Any line
# containing the word "cookie" is dropped outright — in an ESG corpus that word is always
# website boilerplate, never emissions/disclosure/governance content. Bare "consent" is
# NOT a trigger: it's a real ESG term (FPIC — Free, Prior and Informed Consent), so we
# only drop the specific consent-UI phrases below, not the topic.
_BOILERPLATE = (
    "essential site functionality", "accept all", "reject all", "manage preferences",
    "manage consent", "consent selection", "withdraw your consent",
    "your consent applies", "your prior consent", "strictly necessary",
    "learn more about this provider", "maximum storage duration",
    "skip to main content", "opens in a new window", "opens an external website",
    "close this dialog", "privacy policy manage", "preferences statistics marketing",
)


def _strip_boilerplate(text: str) -> str:
    """Drop cookie/consent-banner and window-chrome lines (see ``_BOILERPLATE``)."""
    keep = []
    for ln in text.split("\n"):
        low = ln.lower()
        if "cookie" in low:  # website cookie boilerplate — never ESG content
            continue
        if any(p in low for p in _BOILERPLATE):
            continue
        keep.append(ln)
    return "\n".join(keep)


def _clean_markdown(text: str) -> str:
    """Strip the link/image/nav soup crawl4ai leaves behind so passages read clean.

    Drops images, unwraps ``[label](url)`` to just ``label``, removes bare URLs, deletes
    decoration-only lines, and filters cookie/consent boilerplate — keeping prose, which
    is what we embed and highlight.
    """
    text = _IMG.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _BARE_URL.sub("", text)
    text = _MD_DECOR.sub("", text)
    text = _strip_boilerplate(text)
    return text


def _normalize(text: str) -> str:
    """Clean markdown noise, then collapse whitespace while keeping paragraph breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _clean_markdown(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_markdown(markdown: str) -> list[TextChunk]:
    """Sliding ~512-token windows (64-token overlap) over the normalized text."""
    text = _normalize(markdown)
    if not text:
        return []

    enc = _enc()
    tokens = enc.encode(text)
    if not tokens:
        return []

    step = CHUNK_TOKENS - OVERLAP_TOKENS
    chunks: list[TextChunk] = []
    ordinal = 0
    for start in range(0, len(tokens), step):
        window = tokens[start : start + CHUNK_TOKENS]
        if not window:
            break
        piece = enc.decode(window).strip()
        if piece:
            chunks.append(
                TextChunk(
                    ordinal=ordinal,
                    text=piece,
                    token_count=len(window),
                    content_hash=content_hash(piece),
                )
            )
            ordinal += 1
        if start + CHUNK_TOKENS >= len(tokens):
            break
    return chunks
