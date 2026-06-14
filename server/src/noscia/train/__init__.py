"""Phase 2 quality tooling — eval harness, synthetic-pair generation, fine-tuning.

The eval harness (``eval.py``) is the gate: per CLAUDE.md rule 9 every embedder or
reranker change is decided on ``corpus/eval/esg_queries.jsonl`` (nDCG@10 / MRR /
Recall@10) on the ESG corpus, not on a public leaderboard. ``synth.py`` and
``finetune.py`` produce a candidate; ``eval.py`` says whether it ships.
"""
