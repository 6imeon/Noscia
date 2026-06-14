"""Retrieval eval harness — the gate for every model change (CLAUDE.md rule 9).

Decides embedder/reranker swaps on the **ESG corpus**, not leaderboards. Runs the
held-out queries in ``corpus/eval/esg_queries.jsonl`` through a retriever and reports
**nDCG@10 / MRR / Recall@10**, scored at the **source-domain level**: a query names the
authoritative source(s) that genuinely answer it, and a retrieved chunk counts as
relevant when its page's *domain* is in that set. Domain-level (not exact-URL) is
deliberate — a seed now deep-crawls to many sub-pages, so "did we route to the right
authoritative org" is the honest, churn-proof question; retrieved pages are deduped to
their best rank per domain, since several pages of one source shouldn't each earn credit.

A *retriever* is just ``Callable[[str, int], list[str]]`` → a ranked list of URLs.
That seam is the point: Phase 2a compares the base vs fine-tuned embedder by passing
two retrievers over the *same* query set and the *same* metrics. The built-ins wrap
the live Quality and Fast tiers via the store.

    uv run python -m noscia.train.eval                 # both tiers
    uv run python -m noscia.train.eval --tier quality  # one tier
    uv run python -m noscia.train.eval --k 10 --per-query
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

# A retriever maps (query, k) → ranked URLs (best first), deduped to one per URL.
Retriever = Callable[[str, int], list[str]]

EVAL_PATH = Path(__file__).resolve().parents[4] / "corpus" / "eval" / "esg_queries.jsonl"
DEFAULT_K = 10


@dataclass
class EvalQuery:
    id: str
    query: str
    relevant: set[str]


@dataclass
class QueryScore:
    id: str
    query: str
    ndcg: float
    mrr: float
    recall: float
    first_rank: int | None  # 1-based rank of the first relevant URL (None = miss)


@dataclass
class Report:
    name: str
    k: int
    per_query: list[QueryScore]

    @property
    def ndcg(self) -> float:
        return _mean(s.ndcg for s in self.per_query)

    @property
    def mrr(self) -> float:
        return _mean(s.mrr for s in self.per_query)

    @property
    def recall(self) -> float:
        return _mean(s.recall for s in self.per_query)


def _mean(xs) -> float:
    vals = list(xs)
    return sum(vals) / len(vals) if vals else 0.0


def load_eval(path: Path = EVAL_PATH) -> list[EvalQuery]:
    out: list[EvalQuery] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        out.append(EvalQuery(id=d["id"], query=d["query"], relevant=set(d["relevant"])))
    return out


def _dedupe_keep_order(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    ranked: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ranked.append(u)
    return ranked


def _domain(url: str) -> str:
    """Registrable host (sans leading ``www.``), lowercased — the relevance key.

    Relevance is judged per authoritative source, so every page of a domain shares one
    key; deep-crawl sub-pages and recrawl URL churn don't perturb the gate. A non-URL
    string (the metric tests use bare ``"a"``/``"b"``) falls through to itself.
    """
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or url.strip().lower()


def score_query(ranked_urls: list[str], relevant: set[str], k: int) -> QueryScore:
    """Binary-relevance nDCG@k / MRR / Recall@k over a domain-deduped ranking."""
    relevant_domains = {_domain(u) for u in relevant}
    ranked = _dedupe_keep_order([_domain(u) for u in ranked_urls])[:k]
    gains = [1.0 if d in relevant_domains else 0.0 for d in ranked]

    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal_hits = min(len(relevant_domains), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    ndcg = dcg / idcg if idcg else 0.0

    first_rank = next((i + 1 for i, g in enumerate(gains) if g), None)
    mrr = 1.0 / first_rank if first_rank else 0.0
    recall = (sum(gains) / len(relevant_domains)) if relevant_domains else 0.0
    return QueryScore(id="", query="", ndcg=ndcg, mrr=mrr, recall=recall, first_rank=first_rank)


def evaluate(name: str, retriever: Retriever, queries: list[EvalQuery], k: int) -> Report:
    scores: list[QueryScore] = []
    for q in queries:
        ranked = retriever(q.query, max(k, DEFAULT_K))
        s = score_query(ranked, q.relevant, k)
        scores.append(QueryScore(id=q.id, query=q.query, ndcg=s.ndcg, mrr=s.mrr,
                                  recall=s.recall, first_rank=s.first_rank))
    return Report(name=name, k=k, per_query=scores)


# --- Built-in retrievers over the live store (Quality / Fast tiers) ----------

def quality_retriever(query: str, k: int) -> list[str]:
    from ..search.embed import embed_query
    from ..search.store import get_store

    fused = get_store().hybrid_search(query, embed_query(query), k)
    return [h.chunk.url for h in fused.hits]


def fast_retriever(query: str, k: int) -> list[str]:
    from ..search.embed import embed_query
    from ..search.store import get_store

    fused = get_store().dense_search(embed_query(query), k)
    return [h.chunk.url for h in fused.hits]


RETRIEVERS: dict[str, Retriever] = {
    "quality": quality_retriever,
    "fast": fast_retriever,
}


def _print_report(rep: Report, per_query: bool) -> None:
    print(f"\n{rep.name}  (k={rep.k}, n={len(rep.per_query)})")
    print(f"  nDCG@{rep.k}={rep.ndcg:.3f}   MRR={rep.mrr:.3f}   Recall@{rep.k}={rep.recall:.3f}")
    if per_query:
        print(f"  {'id':<5}{'nDCG':>7}{'MRR':>7}{'rank':>6}  query")
        for s in rep.per_query:
            rank = str(s.first_rank) if s.first_rank else "—"
            print(f"  {s.id:<5}{s.ndcg:>7.3f}{s.mrr:>7.3f}{rank:>6}  {s.query[:54]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="ESG retrieval eval (nDCG@10 / MRR / Recall@10).")
    ap.add_argument("--tier", choices=["quality", "fast", "both"], default="both")
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    ap.add_argument("--per-query", action="store_true", help="print the per-query breakdown")
    args = ap.parse_args()

    queries = load_eval()
    tiers = ["quality", "fast"] if args.tier == "both" else [args.tier]
    print(f"Evaluating {len(queries)} ESG queries from {EVAL_PATH.name}")
    for tier in tiers:
        rep = evaluate(tier, RETRIEVERS[tier], queries, args.k)
        _print_report(rep, args.per_query)


if __name__ == "__main__":
    main()
