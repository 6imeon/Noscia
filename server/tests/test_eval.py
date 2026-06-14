"""Eval-harness metric tests — guard the gate (CLAUDE.md rule 9) with no DB/models.

nDCG@k / MRR / Recall@k are scored at the source-domain level over a deduped ranking.
These pin the arithmetic so a refactor can't silently inflate a model's score.
"""

import math

from noscia.train.eval import _dedupe_keep_order, _domain, score_query


def test_perfect_ranking_scores_one():
    s = score_query(["a", "b"], {"a", "b"}, k=10)
    assert s.ndcg == 1.0
    assert s.mrr == 1.0
    assert s.recall == 1.0
    assert s.first_rank == 1


def test_miss_scores_zero():
    s = score_query(["x", "y", "z"], {"a"}, k=10)
    assert s.ndcg == 0.0
    assert s.mrr == 0.0
    assert s.recall == 0.0
    assert s.first_rank is None


def test_mrr_uses_first_relevant_rank():
    # relevant doc sits at rank 3 → MRR = 1/3
    s = score_query(["x", "y", "a"], {"a"}, k=10)
    assert s.first_rank == 3
    assert math.isclose(s.mrr, 1 / 3)
    # single relevant, single hit → recall is total
    assert s.recall == 1.0


def test_ndcg_discounts_lower_ranks():
    # one relevant doc at rank 2: DCG = 1/log2(3), IDCG = 1/log2(2) = 1
    s = score_query(["x", "a"], {"a"}, k=10)
    assert math.isclose(s.ndcg, 1 / math.log2(3))


def test_recall_is_fraction_of_relevant_found():
    s = score_query(["a", "x", "y"], {"a", "b"}, k=10)
    assert s.recall == 0.5  # found 1 of 2 relevant


def test_dedupe_keeps_best_rank_per_url():
    # several chunks of the same page collapse to its first appearance
    assert _dedupe_keep_order(["a", "a", "b", "a", "c"]) == ["a", "b", "c"]


def test_k_truncates_before_scoring():
    # relevant doc beyond k is not credited
    s = score_query(["x", "y", "a"], {"a"}, k=2)
    assert s.first_rank is None
    assert s.recall == 0.0


def test_domain_strips_scheme_path_and_www():
    assert _domain("https://www.cdp.net/en/companies-discloser") == "cdp.net"
    assert _domain("https://ghgprotocol.org/standards") == "ghgprotocol.org"
    assert _domain("a") == "a"  # non-URL falls through (hermetic metric tests)


def test_relevance_is_domain_level_not_exact_url():
    # a different page of the right authoritative source still counts as relevant
    ranked = ["https://ghgprotocol.org/scope-3-standard"]
    relevant = {"https://ghgprotocol.org/corporate-standard"}  # different path, same domain
    s = score_query(ranked, relevant, k=10)
    assert s.recall == 1.0 and s.first_rank == 1


def test_same_domain_pages_collapse_to_one_credit():
    # two pages of one source shouldn't each earn credit, and recall is per-domain
    ranked = [
        "https://ghgprotocol.org/standards",
        "https://ghgprotocol.org/guidance",
        "https://www.globalreporting.org/standards/",
    ]
    relevant = {"https://ghgprotocol.org/x", "https://www.globalreporting.org/y"}
    s = score_query(ranked, relevant, k=10)
    assert s.recall == 1.0  # both distinct relevant domains found
