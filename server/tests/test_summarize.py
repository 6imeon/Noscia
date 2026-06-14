"""BYOK answer synthesis — no-key path, sentinel, and citation parsing (no network)."""

import asyncio

from noscia.search import summarize as summ


def test_no_key_returns_no_answer(monkeypatch):
    monkeypatch.setattr(summ, "get_secret", lambda _name: None)
    assert asyncio.run(summ.synthesize_answer("q", ["passage a", "passage b"])) == (None, [])


def test_empty_passages_short_circuit(monkeypatch):
    monkeypatch.setattr(summ, "get_secret", lambda _name: "sk-test")
    assert asyncio.run(summ.synthesize_answer("q", ["   ", ""])) == (None, [])


def test_parse_extracts_answer_and_citations():
    answer, cited = summ._parse("Governance and strategy are two of them [1][3].", n=6)
    assert answer == "Governance and strategy are two of them [1][3]."
    assert cited == [1, 3]


def test_parse_drops_out_of_range_and_dedupes_citations():
    _, cited = summ._parse("See [2], [2] and [9].", n=6)  # 9 > n, dropped; 2 deduped
    assert cited == [2]


def test_parse_none_sentinel_but_keeps_real_none_answer():
    assert summ._parse("NONE", 6) == (None, [])
    assert summ._parse("NONE.", 6) == (None, [])
    # a real answer that merely starts with "None" survives
    ans, _ = summ._parse("None of the sources name a Scope 3 target [1].", 6)
    assert ans == "None of the sources name a Scope 3 target [1]."
