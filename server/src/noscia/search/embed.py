"""Embedding model seam — Qwen3-Embedding-0.6B (SPEC §4, IMPLEMENTATION §1).

Local, in-process embeddings via ``sentence-transformers`` (the dev-loop runtime;
the deployed box swaps to batched TEI behind the same call sites). Qwen3 emits
1024-dim vectors with native **Matryoshka** support: we truncate to ``EMBED_DIM``
(256) and renormalize — a storage/quality point chosen in the SPEC, to be revisited
only via the eval harness (CLAUDE.md rule 9), never by leaderboard.

Asymmetric retrieval: **queries** get Qwen3's instruction prompt; **documents** are
embedded raw. Mixing the two up silently tanks recall, so the two entry points are
kept separate on purpose.

The model (~600 MB) downloads on first use and is cached under ``data/models`` (or
the HF cache). Loading is lazy + cached so importing this module stays cheap.
"""

from __future__ import annotations

import threading
from functools import lru_cache

from .store import EMBED_DIM

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"

# The retrieval instruction Qwen3 expects on the *query* side. Documents get none.
QUERY_INSTRUCTION = (
    "Given an ESG, sustainability, or corporate-disclosure question, "
    "retrieve passages that answer it"
)

_load_lock = threading.Lock()


def _pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@lru_cache(maxsize=1)
def _model():
    """Load (once) the Qwen3 embedder, truncated to EMBED_DIM via Matryoshka."""
    from sentence_transformers import SentenceTransformer

    # Double-checked locking: lru_cache makes the *result* singleton, the lock keeps
    # two first-callers from each paying the load cost concurrently.
    with _load_lock:
        return SentenceTransformer(
            MODEL_NAME,
            truncate_dim=EMBED_DIM,  # Matryoshka: 1024 → 256
            device=_pick_device(),
        )


def embed_query(text: str) -> list[float]:
    """Embed a single search query (instruction-prefixed, 256-dim, L2-normalized)."""
    vec = _model().encode(
        [text],
        prompt=f"Instruct: {QUERY_INSTRUCTION}\nQuery: ",
        normalize_embeddings=True,  # renormalize after the Matryoshka truncation
        convert_to_numpy=True,
    )[0]
    return vec.tolist()


def embed_docs(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    """Embed document chunks raw (no instruction), 256-dim, L2-normalized."""
    if not texts:
        return []
    vecs = _model().encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=len(texts) > 64,
    )
    return [v.tolist() for v in vecs]


def warm() -> None:
    """Force the model to load now (e.g. at server startup) instead of on first query."""
    _model()
