from fastapi.testclient import TestClient

from noscia.app import app

client = TestClient(app)


def test_health_shape():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert isinstance(body["db"], bool)
    assert isinstance(body["version"], str)
    # status reflects DB reachability
    assert body["status"] == ("ok" if body["db"] else "degraded")


def test_search_runs_pipeline_and_is_contract_valid(monkeypatch):
    # /search now runs the real pipeline (embed → retrieve → rerank → highlight).
    # Mock it so the endpoint/contract is tested without loading models or the DB.
    from noscia import app as app_mod
    from noscia.contract import PipelineTrace, SearchResponse, SearchResult

    def fake(req):
        return SearchResponse(
            query=req.query,
            tier=req.tier,
            results=[
                SearchResult(
                    rank=1,
                    url="https://example.org/x",
                    title="A passage",
                    source_type="framework",
                    score=0.5,
                    highlight="<mark>scope</mark> 3 emissions",
                )
            ],
            trace=PipelineTrace(dense=1, bm25=0, fused=1, reranked=0),
        )

    monkeypatch.setattr(app_mod, "run_search", fake)
    r = client.post("/search", json={"query": "scope 3 emissions", "tier": "fast"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "scope 3 emissions"
    assert body["tier"] == "fast"
    assert len(body["results"]) == 1
    assert "<mark>" in body["results"][0]["highlight"]
    assert set(body["trace"]) == {"dense", "bm25", "fused", "reranked"}


def test_search_rejects_empty_query():
    r = client.post("/search", json={"query": "", "tier": "quality"})
    assert r.status_code == 422


def test_providers_masked_only():
    r = client.get("/providers")
    assert r.status_code == 200
    body = r.json()
    assert body["default_provider"] == "openrouter"
    p = body["providers"][0]
    assert set(p) == {"provider", "configured", "masked"}
    # never leak a raw key: masked is short or empty
    assert "…" in p["masked"] or p["masked"] == "" or set(p["masked"]) == {"•"}
