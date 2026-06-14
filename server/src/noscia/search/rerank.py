"""Reranking — cross-encoder over the fused top-k (SPEC §4, IMPLEMENTATION §1).

``bge-reranker-v2-m3`` is the default; ``Qwen3-Reranker-0.6B`` is the eval-gated
alternative (CLAUDE.md rule 9). The cross-encoder scores each (query, passage) pair
jointly — far sharper than the bi-encoder used for retrieval, but too slow to run
over the whole corpus, so it only re-orders the fused candidates. Lazy-loaded.
"""

from __future__ import annotations

from functools import lru_cache

from .store import Hit

MODEL_NAME = "BAAI/bge-reranker-v2-m3"


def _pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(MODEL_NAME, device=_pick_device())


def rerank(query: str, hits: list[Hit], top_k: int) -> list[Hit]:
    """Re-score hits with the cross-encoder; return the top_k, highest first.

    Scores are sigmoid-squashed to 0–1 so the UI score bar is interpretable.
    """
    if not hits:
        return []
    import numpy as np

    pairs = [(query, h.chunk.text) for h in hits]
    raw = _model().predict(pairs, convert_to_numpy=True)
    probs = 1.0 / (1.0 + np.exp(-raw))  # logits → 0–1

    rescored = [Hit(chunk=h.chunk, score=float(p)) for h, p in zip(hits, probs, strict=False)]
    rescored.sort(key=lambda h: h.score, reverse=True)
    return rescored[:top_k]


def warm() -> None:
    _model()
