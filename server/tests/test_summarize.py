"""BYOK summary synthesis — the no-key + sentinel paths (no network)."""

import asyncio

from noscia.search import summarize as summ


def test_no_key_returns_all_none(monkeypatch):
    monkeypatch.setattr(summ, "get_secret", lambda _name: None)
    out = asyncio.run(summ.summarize("q", ["passage a", "passage b"]))
    assert out == [None, None]


def test_empty_passages_short_circuit(monkeypatch):
    # Even with a key, no passages means no calls and no error.
    monkeypatch.setattr(summ, "get_secret", lambda _name: "sk-test")
    assert asyncio.run(summ.summarize("q", [])) == []


def test_clean_maps_none_sentinel_and_trims():
    assert summ._clean("NONE") is None
    assert summ._clean("NONE.") is None
    assert summ._clean("  none, the passage is unrelated") is None  # leading sentinel
    assert summ._clean("   ") is None
    assert summ._clean("  The four elements are governance and strategy.  ") == (
        "The four elements are governance and strategy."
    )
    # a real answer that merely *starts* with "None" must survive the sentinel check
    assert summ._clean("None of the companies disclose a Scope 3 target.") == (
        "None of the companies disclose a Scope 3 target."
    )
