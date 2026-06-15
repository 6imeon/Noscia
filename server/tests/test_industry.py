"""Multi-industry scope key (MULTI_INDUSTRY.md Phase A) — no DB, no models.

Two guarantees, both runnable without Postgres:
  1. retrieval is *physically* scoped — both legs of the hybrid CTE and the dense leg
     carry `WHERE industry = :industry`, and the upsert writes the column; and
  2. the scope is *wired through* — `run_search` forwards `req.industry` to the store
     and defaults it to 'esg', so a request never bleeds across verticals and existing
     single-corpus callers keep working unchanged.
"""

import types

import pytest

from noscia import corpus
from noscia.contract import (
    AddSeedRequest,
    CorpusResponse,
    IngestRequest,
    RemoveSeedRequest,
    SearchRequest,
    StructuredRequest,
)
from noscia.search import pipeline
from noscia.search.store import _DENSE_SQL, _HYBRID_SQL, _UPSERT_SQL, Chunk, Fused


# --- 1. the predicate is in the SQL --------------------------------------
def test_both_hybrid_legs_filter_by_industry():
    sql = str(_HYBRID_SQL)
    # one predicate per retrieval CTE (dense + lexical), not just one of them
    assert sql.count("industry = :industry") == 2


def test_dense_leg_filters_by_industry():
    assert "industry = :industry" in str(_DENSE_SQL)


def test_upsert_writes_industry_column():
    sql = str(_UPSERT_SQL)
    assert ":industry" in sql and "industry = EXCLUDED.industry" in sql


def test_chunk_defaults_to_esg():
    c = Chunk(id="x", url="u", title="t", text="b", source_type="report", dense=[])
    assert c.industry == "esg"


# --- 2. the scope is threaded through run_search -------------------------
def _fake_store(calls: dict):
    def dense_search(dense, top_k, industry="esg"):
        calls["industry"] = industry
        return Fused(hits=[], dense_n=0, bm25_n=0)

    def hybrid_search(query, dense, top_k, industry="esg"):
        calls["industry"] = industry
        return Fused(hits=[], dense_n=0, bm25_n=0)

    return types.SimpleNamespace(dense_search=dense_search, hybrid_search=hybrid_search)


def test_run_search_forwards_industry_fast_tier(monkeypatch):
    calls: dict = {}
    monkeypatch.setattr(pipeline, "embed_query", lambda _q: [0.0] * 256)
    monkeypatch.setattr(pipeline, "get_store", lambda: _fake_store(calls))

    pipeline.run_search(SearchRequest(query="q", tier="fast", industry="economics"))
    assert calls["industry"] == "economics"

    pipeline.run_search(SearchRequest(query="q", tier="fast"))  # default
    assert calls["industry"] == "esg"


def test_run_search_forwards_industry_quality_tier(monkeypatch):
    calls: dict = {}
    monkeypatch.setattr(pipeline, "embed_query", lambda _q: [0.0] * 256)
    monkeypatch.setattr(pipeline, "get_store", lambda: _fake_store(calls))
    monkeypatch.setattr(pipeline.rerank_mod, "rerank", lambda _q, hits, _k: hits)

    pipeline.run_search(SearchRequest(query="q", tier="quality", industry="healthcare"))
    assert calls["industry"] == "healthcare"


# --- source removal (Phase A′): industry-scoped, drops chunks + the sources row ---
def test_corpus_delete_source_is_industry_scoped_and_drops_both(monkeypatch):
    """corpus.delete_source drops the seed's chunks via the store *and* its sources row,
    both filtered by (url, industry) — so removing from one vertical can't touch another."""
    store_call: dict = {}
    monkeypatch.setattr(
        corpus,
        "get_store",
        lambda: types.SimpleNamespace(
            delete_source=lambda src, industry: store_call.update(src=src, industry=industry) or 7
        ),
    )
    sql_seen: list[tuple[str, dict]] = []

    class _Conn:
        def execute(self, stmt, params):
            sql_seen.append((str(stmt), params))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        corpus.db, "get_engine", lambda: types.SimpleNamespace(begin=lambda: _Conn())
    )

    removed = corpus.delete_source("https://seed", "economics")
    assert removed == 7  # the chunk count the store reported (UI confirms this)
    assert store_call == {"src": "https://seed", "industry": "economics"}
    # the sources row is deleted with the same (url, industry) scope
    stmt, params = sql_seen[-1]
    assert "DELETE FROM sources" in stmt
    assert params == {"url": "https://seed", "industry": "economics"}


def test_remove_seed_request_defaults_industry_to_esg():
    assert RemoveSeedRequest(url="u").industry == "esg"


def test_nullable_industry_filter_casts_the_bound_param():
    """Regression: the `industry IS NULL ⇒ all verticals` filter must CAST the bound param.

    Postgres can't infer a bare param's type in `:industry IS NULL` (AmbiguousParameter),
    and SQLAlchemy's text() mis-parses the `::text` shorthand against its own `:name` binds —
    so the only form that both compiles and runs is `CAST(:industry AS text) IS NULL`. Tests
    have no live DB, so guard the SQL text directly: this 500'd the /corpus view in practice.
    """
    import pathlib

    src = pathlib.Path(corpus.__file__).read_text()
    assert "CAST(:industry AS text) IS NULL" in src
    assert ":industry IS NULL" not in src  # the bare, type-ambiguous form
    assert ":industry::text" not in src  # the SQLAlchemy-incompatible cast form


def test_filtered_ann_queries_raise_ef_search():
    """Regression: both ANN queries must widen `hnsw.ef_search` before running.

    With the per-vertical `WHERE industry = …` filter applied *after* the HNSW traversal, the
    default `ef_search` (40, < PREFETCH) starves a sparse vertical — a real economics query
    returned 0 dense hits until this landed. Guard the SQL text (no live DB here): both
    `hybrid_search` and `dense_search` issue `SET LOCAL hnsw.ef_search`, and EF_SEARCH ≥ PREFETCH.
    """
    import pathlib

    from noscia.search import store as store_mod

    src = pathlib.Path(store_mod.__file__).read_text()
    assert src.count("SET LOCAL hnsw.ef_search") == 2  # one per ANN method
    assert store_mod.EF_SEARCH >= store_mod.PREFETCH


# --- 3. every industry-carrying contract model defaults to esg -----------
def test_contract_models_default_industry_to_esg():
    assert SearchRequest(query="q").industry == "esg"
    assert StructuredRequest(query="q").industry == "esg"
    assert IngestRequest().industry == "esg"
    assert AddSeedRequest(url="u", source_type="report").industry == "esg"
    # CorpusResponse carries the field too (asserted via its declared default)
    assert CorpusResponse.model_fields["industry"].default == "esg"


# --- Phase B: catalog + selection ----------------------------------------
def test_catalog_lists_esg_with_a_seed_file():
    from noscia.ingest import run as ingest

    cat = ingest.load_industries()
    esg = next((c for c in cat if c["id"] == "esg"), None)
    assert esg is not None, "esg must be in corpus/industries.yaml"
    assert esg["seeds"] == "seeds/esg.yaml"
    assert esg["label"] and esg["blurb"] and esg["icon"]  # picker card fields present


def test_seeds_path_resolves_to_existing_file():
    from noscia.ingest import run as ingest

    p = ingest.seeds_path("esg")
    assert p.name == "esg.yaml" and p.exists()  # the relocated, byte-identical seed file


def test_seeds_path_unknown_industry_raises():
    from noscia.ingest import run as ingest

    with pytest.raises(ValueError):
        ingest.seeds_path("does-not-exist")


# --- v1 catalog: all 10 verticals are selectable, each backed by a real seed file --------
# The 9 non-ESG verticals ship as *options only* — no corpus is pre-embedded; the first
# /industries/select of one kicks off its crawl (IndustrySetup → /corpus/ingest). This test
# guards that every catalog entry is complete and its seed list parses (so the picker can't
# offer a field that 404s on first load).
def test_catalog_has_ten_verticals_each_with_a_parseable_seed_list():
    import yaml

    from noscia.ingest import run as ingest

    cat = ingest.load_industries()
    ids = {c["id"] for c in cat}
    expected = {
        "esg", "economics", "healthcare", "cybersecurity", "ai",
        "energy", "finance", "agriculture", "pharma", "space",
    }
    assert ids == expected, f"catalog drift: {ids ^ expected}"

    for entry in cat:
        assert entry["label"] and entry["blurb"] and entry["icon"]  # picker card fields
        path = ingest.seeds_path(entry["id"])
        assert path.exists(), f"{entry['id']} seed file missing: {path}"
        doc = yaml.safe_load(path.read_text())
        seeds = doc.get("seeds") or []
        assert seeds, f"{entry['id']} has no seeds"
        for s in seeds:
            assert s.get("url", "").startswith("http"), f"{entry['id']} seed missing url: {s}"
            assert s.get("source_type"), f"{entry['id']} seed missing source_type: {s}"


def test_industries_response_marks_active_and_loaded(monkeypatch):
    from noscia import app as app_mod

    monkeypatch.setattr(app_mod.user_mod, "get_active_industry", lambda _u: "esg")
    monkeypatch.setattr(app_mod.corpus, "industries_loaded", lambda: {"esg"})

    resp = app_mod._industries_for(app_mod.user_mod.SOLO_USER)
    assert resp.active == "esg"
    esg = next(i for i in resp.industries if i.id == "esg")
    assert esg.active and esg.loaded  # the one crawled vertical is both


def test_select_unknown_industry_is_404(monkeypatch):
    from fastapi import HTTPException

    from noscia import app as app_mod
    from noscia.contract import SelectIndustryRequest

    with pytest.raises(HTTPException) as ei:
        # request arg unused (current_user → SoloUser), so None is fine here
        app_mod.industries_select(SelectIndustryRequest(id="nope"), None)
    assert ei.value.status_code == 404


def test_select_persists_then_returns_updated_catalog(monkeypatch):
    from noscia import app as app_mod
    from noscia.contract import SelectIndustryRequest

    saved: dict = {}
    monkeypatch.setattr(
        app_mod.user_mod, "set_active_industry", lambda _u, ind: saved.update(industry=ind)
    )
    monkeypatch.setattr(
        app_mod.user_mod, "get_active_industry", lambda _u: saved.get("industry", "esg")
    )
    monkeypatch.setattr(app_mod.corpus, "industries_loaded", lambda: {"esg"})

    resp = app_mod.industries_select(SelectIndustryRequest(id="esg"), None)
    assert saved["industry"] == "esg"  # persisted
    assert resp.active == "esg"  # and reflected back
