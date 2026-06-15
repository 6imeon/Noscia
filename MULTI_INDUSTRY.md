# Multi-industry corpora — design & implementation plan

Status: **proposal / research** (not yet built). Author notes for the next phase.
Read [SPEC.md](SPEC.md) and [IMPLEMENTATION.md](IMPLEMENTATION.md) first; this doc extends them.

## 1. The goal

Today Noscia is a single, hard-wired **ESG** corpus. We want it to become a
**multi-vertical** product where the *vertical* is chosen, not compiled in:

- On first login the user is greeted with a **setup menu** and picks **one field**
  (ESG, Economics, …). That choice is the only thing they configure to get started.
- Each field ships a **curated seed list** (its authoritative sites/links), so picking
  a field is enough to begin crawling its corpus.
- A user has **exactly one industry active at a time** ("loaded"). They can switch
  later, but search/answer/structured all operate on the active one only.

This is a natural extension of **rule 11 — keep the corpus narrow and vertical**: we're
not widening any single corpus, we're letting the *same machinery* host several narrow
verticals and surfacing one at a time. It does **not** touch rule 13 (still index-only,
no third-party search) — each vertical is still our own curated, crawled index.

## 2. What exists today (the seams we build on)

The good news: the pipeline (crawl → chunk → embed → store → hybrid retrieve) is already
corpus-agnostic. Nothing about it assumes "ESG" except *which seed file we load* and the
fact that **no column scopes a chunk to a corpus**. The single-corpus assumption lives in
exactly five places:

| Layer | Where | Single-corpus coupling |
|---|---|---|
| Seeds | [corpus/seeds.esg.yaml](corpus/seeds.esg.yaml) + `SEEDS_PATH` in [server/src/noscia/ingest/run.py](server/src/noscia/ingest/run.py) | One hard-coded YAML path, ESG-only. |
| Schema | [db/init/02-schema.sql](db/init/02-schema.sql) `chunks` / `sources` | No `industry` column — one undifferentiated pool. |
| Store | `VectorStore` / `PgVectorStore` in [server/src/noscia/search/store.py](server/src/noscia/search/store.py) | `hybrid_search` / `dense_search` have no scope predicate. |
| Contract | `SearchRequest` etc. in [server/src/noscia/contract.py](server/src/noscia/contract.py) ⇄ [web/src/lib/api.ts](web/src/lib/api.ts) | No `industry` field anywhere. |
| User / UI | `current_user()` in [server/src/noscia/user.py](server/src/noscia/user.py); `App.tsx` boots straight to search | No stored preference, no first-run gate. |

Two facts make this cheap:

1. **`current_user()` is already a seam** ([user.py](server/src/noscia/user.py)) — designed
   for an SSO swap. The "active industry" is a per-user preference and belongs here.
2. The store interface is small and abstract ([store.py](server/src/noscia/search/store.py)
   lines 87–133). Adding one optional `industry` arg threads cleanly through `run_search`.

## 3. The core decision: how is "one industry loaded at a time" realised?

Two viable models. **They differ only in whether non-active corpora stay in the DB.**

### Model A — Partition column (recommended)

Add `industry TEXT NOT NULL` to `chunks` and `sources`. Every crawl tags its rows.
Every query filters `WHERE industry = :active`. All crawled verticals **coexist** in
Postgres; "loaded" is just *the active filter*, stored per user.

- ✅ **Switching is instant** — flip the filter, no recrawl, no data loss.
- ✅ Crawl each vertical **once**; revisit cadence-only (`--due`).
- ✅ Minimal schema change; reuses the whole existing pipeline.
- ⚠️ All verticals' embeddings share one HNSW/BM25 index. Filtered ANN can lose recall
    if a vertical is a small slice of a huge index — mitigated below (§5.1).
- ⚠️ Disk grows with total corpora (fine — text + 256-dim vectors are small; a
    ~300–500 page vertical is tens of MB).

### Model B — Physical swap (single loaded corpus)

Only the active vertical's rows physically live in `chunks` at any moment. Switching =
wipe + recrawl (or swap to a per-industry table/schema).

- ✅ Literally matches "one loaded at a time"; smallest possible index → best recall.
- ❌ Switching costs a **full recrawl** (minutes, network, the 18 GB box does embeddings).
  That's a bad UX for "let me check Economics for a sec."
- ❌ Throwaway work — you re-pay crawl+embed every switch.

### Recommendation

**Model A**, with the *product* constraint ("one at a time") enforced at the **session/UI
layer**, not by destroying data. Crawl-once-switch-instantly is strictly better UX and
respects the 18 GB box (we never recrawl just to switch). If true isolation is ever needed
(e.g. per-tenant data separation), Model A upgrades cleanly to **Postgres declarative
partitioning** (`PARTITION BY LIST (industry)`), giving each vertical its own HNSW + BM25
index and physical isolation *without* changing query code — see §5.1.

> One embedding model for all verticals. We keep the single shared Qwen3 embedder +
> bge reranker. Vertical quality comes from the **corpus**, not a per-field model. A
> per-vertical model swap would be a separate, **eval-gated** change (rule 9) and is out
> of scope here.

## 4. The industry catalog

> The concrete v1 catalog — **10 verticals with curated authoritative seed lists** (ESG,
> Economics, Healthcare, Cybersecurity, AI, Energy, Finance, Agriculture, Pharma, Space) —
> lives in [corpus/INDUSTRIES.md](corpus/INDUSTRIES.md), ready to split into the
> `corpus/seeds/<id>.yaml` files described below.

Industries are **static config**, not user data — so a checked-in manifest, not a DB table.

```
corpus/
  industries.yaml          # the catalog: id, label, blurb, icon, seed file
  seeds/
    esg.yaml               # ← today's seeds.esg.yaml, moved here
    economics.yaml
    ...
```

`corpus/industries.yaml`:

```yaml
industries:
  - id: esg                # stable slug — the value stored in chunks.industry
    label: "ESG & Sustainability"
    blurb: "Standards, regulators, ratings, and target-setters for corporate sustainability."
    icon: leaf             # maps to a frontend icon
    seeds: seeds/esg.yaml
  - id: economics
    label: "Economics"
    blurb: "Central banks, statistical agencies, and macro research."
    icon: chart
    seeds: seeds/economics.yaml
```

The per-industry seed file keeps **today's exact schema** (no change to a seed's shape —
`url` / `source_type` / `org` / `cadence` / `crawl:`). The `source_type` literals
(`framework | regulator | ratings | report | ngo | news`) are ESG-flavoured; for other
verticals we either reuse them loosely or widen the `SourceType` literal later (a contract
change, deferred — not needed for v1; Economics sources still map onto
regulator/report/news reasonably).

Backwards-compat: `corpus/seeds.esg.yaml` → `corpus/seeds/esg.yaml` with `industry: esg`.
Existing crawled rows get backfilled to `industry = 'esg'` (§7).

## 5. Backend changes

### 5.1 Schema ([db/init/02-schema.sql](db/init/02-schema.sql))

```sql
ALTER TABLE chunks  ADD COLUMN IF NOT EXISTS industry TEXT NOT NULL DEFAULT 'esg';
ALTER TABLE sources ADD COLUMN IF NOT EXISTS industry TEXT NOT NULL DEFAULT 'esg';
CREATE INDEX IF NOT EXISTS chunks_industry_idx  ON chunks  (industry);
CREATE INDEX IF NOT EXISTS sources_industry_idx ON sources (industry);
```

The `DEFAULT 'esg'` is exactly the migration: every existing row becomes ESG with no
data move. `sources` PK becomes effectively `(industry, url)` in spirit — keep `url` PK
for now since the same authoritative URL is unlikely to span verticals; revisit if it does.

**Recall under filtering (the one real risk).** pgvector HNSW with a `WHERE industry=…`
post-filter can under-return if the active vertical is a thin slice of a large index. Two
mitigations, in order of effort:

1. **MVP:** raise `hnsw.ef_search` and/or `PREFETCH` (currently 100,
   [store.py](server/src/noscia/search/store.py) line ~27) so each leg over-fetches before
   the filter. Cheap; sufficient while total index is small (a few verticals × ~400 pages).
2. **If it grows:** convert `chunks` to **`PARTITION BY LIST (industry)`** with a per-
   partition HNSW + BM25 index. Queries already carry `WHERE industry=…` → Postgres prunes
   to one partition → ANN runs over only that vertical (full recall) with **no query
   rewrite**. Verify ParadeDB `pg_search` BM25 indexes are supported on partitions before
   committing (flagged unknown — test on the ParadeDB 0.24 image).

### 5.2 Store ([store.py](server/src/noscia/search/store.py))

Add `industry: str` to the abstract `hybrid_search`, `dense_search`, `count`, and the
incremental-crawl helpers, and inject the predicate into both retrieval CTEs:

```sql
-- in dense AS (...) and lexical AS (...):
WHERE industry = :industry
  -- lexical leg keeps its @@@ match: AND id @@@ paradedb.match('text', :q)
```

`upsert` reads `industry` off each `Chunk`. Add `industry: str` to the `Chunk` dataclass
(default `'esg'` for safety). `count()` and `prune_pages()` gain the scope too.

### 5.3 Contract ([contract.py](server/src/noscia/contract.py) ⇄ [api.ts](web/src/lib/api.ts))

Rule 5 — change both sides together, types matching exactly.

```python
# new
class Industry(BaseModel):
    id: str
    label: str
    blurb: str
    icon: str
    active: bool          # is this the caller's currently-loaded vertical
    loaded: bool          # has it been crawled (sources/chunks exist)

class IndustriesResponse(BaseModel):
    industries: list[Industry]
    active: str           # active industry id for this user

# changed: every retrieval/corpus request carries the active vertical
class SearchRequest(BaseModel):
    ...
    industry: str = "esg"        # default keeps existing callers working

# StructuredRequest, IngestRequest, AddSeedRequest, CorpusResponse all gain `industry`
```

### 5.4 User preference ([user.py](server/src/noscia/user.py))

The active industry is a **per-user** preference. Persist it keyed by `User.id`:

```sql
CREATE TABLE IF NOT EXISTS user_prefs (
    user_id          TEXT PRIMARY KEY,
    active_industry  TEXT NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`SoloUser` → one row (`user_id = 'solo'`). When SSO lands, the row is keyed by the SSO
user with zero call-site change — same seam the file already advertises. A helper
`get_active_industry(user)` / `set_active_industry(user, id)` lives next to `current_user`.

> Defensive default: if a request omits `industry`, the server resolves it from
> `user_prefs` (falling back to `esg`). The client should always send it explicitly once
> the setup gate exists; the default is belt-and-braces.

### 5.5 Endpoints ([app.py](server/src/noscia/app.py))

New:

- `GET /industries` → `IndustriesResponse` — catalog from `industries.yaml`, each marked
  `loaded` (has rows) and `active` (matches the user's pref). Drives the setup menu.
- `POST /industries/select {id}` → sets `user_prefs.active_industry`, returns the updated
  `IndustriesResponse`. If the chosen vertical isn't `loaded`, the response signals the
  client to kick off ingest.

Changed: `/search`, `/structured`, `/corpus`, `/corpus/ingest`, `/corpus/add` all become
**industry-scoped** — read it from the request (preferred) or the user pref. The in-memory
search cache key (`OrderedDict` keyed by `(query, tier)` in [app.py](server/src/noscia/app.py))
becomes `(industry, query, tier)` so two verticals never collide.

### 5.6 Ingest ([ingest/run.py](server/src/noscia/ingest/run.py))

- `SEEDS_PATH` → resolve from `industries.yaml` by id. `load_seeds(industry)` reads
  `corpus/seeds/<industry>.yaml`; `register_seeds(industry)` tags `sources.industry`.
- Every `Chunk(...)` in `_index_page` sets `industry=<the crawl's industry>`.
- CLI gains `--industry <id>` (default `esg`):
  `uv run python -m noscia.ingest.run --industry economics`
  `--due` honours it too (recrawl one vertical's overdue seeds).
- `prune_pages` / `existing_hashes` scope by industry so verticals never prune each other.

### 5.7 Source management — add **and remove** URL sources

A vertical isn't static: the user curates it. **Adding already works**; **removing does
not** — that's the gap to close.

**Add (exists):** `POST /corpus/add` ([app.py](server/src/noscia/app.py) line 217) upserts a
seed via `corpus.upsert_source` and crawls it with `ingest.ingest_specs([spec])`.
`POST /corpus/ingest` re-crawls all or a named subset. Both just gain the `industry` tag
(§5.3) so a new seed lands in the active vertical.

**Remove (to build):** there is no endpoint and no helper to delete a source. The store
already has the primitive — `delete_url(url)` and `delete_ids(ids)`
([store.py](server/src/noscia/search/store.py) lines 87–133) — but nothing removes *a seed
and all the chunks it produced*. Every chunk carries `source_url` (the seed it was
discovered under), so one predicate covers a seed's entire footprint, deep-crawl pages
included:

```python
# store.py — new VectorStore method
def delete_source(self, source_url: str, industry: str) -> int:
    """Drop every chunk discovered under a seed (the seed page + all deep-crawled
    pages). Returns rows removed."""
    # DELETE FROM chunks WHERE source_url = :source_url AND industry = :industry
```

```python
# corpus.py — new helper: remove the seed row + its embeddings, atomically
def delete_source(url: str, industry: str) -> int:
    removed = get_store().delete_source(url, industry)
    with db.get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM sources WHERE url = :url AND industry = :industry"),
            {"url": url, "industry": industry},
        )
    return removed
```

```python
# contract.py ⇄ api.ts (rule 5 — both sides together)
class RemoveSeedRequest(BaseModel):
    url: str
    industry: str = "esg"

class RemoveSeedResponse(BaseModel):
    ok: bool
    removed_chunks: int
```

```python
# app.py — new endpoint
@app.post("/corpus/remove", response_model=RemoveSeedResponse)
def corpus_remove(req: RemoveSeedRequest) -> RemoveSeedResponse:
    removed = corpus.delete_source(req.url, req.industry)
    return RemoveSeedResponse(ok=True, removed_chunks=removed)
```

Notes:
- **Confirm-before-delete** in the UI — removing a seed throws away its crawl+embed work;
  re-adding re-pays it. Show the chunk count that will be dropped.
- A **re-crawl/refresh** action per source is just `POST /corpus/ingest {urls:[url]}` —
  already supported; surface it as a per-row "↻ Refresh" next to "Remove".
- Removal is **industry-scoped** so you can only delete from the vertical you're in.

**Corpus view UI** ([web/src/views/](web/src/views/)): each source row gains **Remove** (with
confirm) and **Refresh**. "Add source" already has a path (`/corpus/add`); keep its form and
tag the active industry automatically.

## 6. Frontend changes

### 6.1 First-run setup gate

Today `App.tsx` boots straight to the search Rail with no onboarding and no localStorage.
Add:

- A top-level `activeIndustry` state in `App.tsx` (lifted above the Rail/views), seeded
  from `GET /industries` on mount.
- If `active` is unset (new user) → render a **full-screen `IndustrySetup` modal** instead
  of the Rail: cards from `/industries` (label + blurb + icon), pick one → `POST
  /industries/select` → if not `loaded`, transition into an **ingest/“building your
  corpus” progress** state, then drop into search.
- Persist the choice client-side (localStorage) as a fast-path so the gate doesn't flash
  on every reload; the server pref remains source of truth.

### 6.2 Switching later

- A small **industry switcher** in the Rail header (shows the active label; click → the
  same picker). Switching = `POST /industries/select` + clear current results. Instant
  under Model A (no recrawl) when the target is already `loaded`; otherwise shows the
  build-progress state.

### 6.3 Plumbing

- `web/src/lib/api.ts`: add `industries()` / `selectIndustry(id)`; add `industry` to
  `SearchRequest` / `StructuredRequest` bodies. The Search view passes the active industry
  into every call (lift it via prop/context from `App`).
- Corpus view ([views](web/src/views/)) already lists sources — scope it to the active
  industry and show which vertical you're looking at.

## 7. Migration & rollout

Zero-downtime, because every change defaults to `esg`:

1. **Schema:** `ALTER TABLE … ADD COLUMN industry … DEFAULT 'esg'` backfills every existing
   chunk/source in place. No data move, no recrawl.
2. **Files:** move `seeds.esg.yaml` → `seeds/esg.yaml`; add `industries.yaml` with the
   `esg` entry; keep its content byte-identical.
3. **Backend:** ship contract + store + endpoint changes; `industry` defaults to `esg`
   everywhere, so the app behaves exactly as today until a second vertical is added.
4. **Frontend:** ship the gate; for the existing single-vertical state it auto-selects
   `esg` (the only `loaded` one) so nothing regresses.
5. **Second vertical:** author `seeds/economics.yaml`, add to `industries.yaml`, crawl via
   `--industry economics`. Now the picker has two real options.

### Suggested phasing

- **Phase A — backend scoping (invisible):** schema column, store predicate, contract
  `industry` field defaulting to `esg`, ingest `--industry`. Everything still ESG; full
  test/eval parity proves no regression.
- **Phase B — catalog + selection:** `industries.yaml`, `/industries`, `/industries/select`,
  `user_prefs`. Still one vertical, but selectable end-to-end.
- **Phase C — onboarding UX:** the first-run gate + Rail switcher.
- **Phase D — second vertical:** prove the whole thing by adding Economics seeds and
  crawling them.

## 8. Open questions (decide before building)

1. **Model A vs B** — confirm "loaded = active filter, crawl-once" (A) vs "physically one
   corpus, recrawl on switch" (B). This doc recommends **A**.
2. **`SourceType` per vertical** — reuse the ESG literals for all verticals (v1), or make
   the type set per-industry (later contract change)? Recommend reuse for v1.
3. **Who can crawl?** Is triggering a vertical's first crawl an admin action or any user's?
   (`User.is_admin` already exists.) Matters once SSO lands.
4. **Eval per vertical** — rule 9 gates model changes on `corpus/eval/esg_queries.jsonl`.
   A new vertical wants its own `eval/<id>_queries.jsonl` before we trust its ranking.
   Not a blocker for v1 UX, but the honest gate before claiming a vertical is "good."
5. **Switching cost messaging** — even under Model A, the *first* load of a vertical is a
   crawl. The setup/switch UX must show real progress (reuse the Corpus ingest status).

## 9. Phased implementation checklist

Each phase is **independently shippable** because everything defaults to `esg`. Run the
full gate after each (`ruff` + `pytest`, `eslint` + `tsc` + `vitest` + build) and update
`CHANGELOG.md` at each phase's end (rule 12). Contract changes touch
[contract.py](server/src/noscia/contract.py) **and** [api.ts](web/src/lib/api.ts) together
(rule 5).

### Phase A — backend scoping (invisible; still 100% ESG) ✅ done 2026-06-15
- [x] **Schema:** add `industry TEXT NOT NULL DEFAULT 'esg'` to `chunks` + `sources`;
      add `chunks_industry_idx`, `sources_industry_idx` ([db/init/02-schema.sql](db/init/02-schema.sql), idempotent `ADD COLUMN IF NOT EXISTS`).
- [x] **Store:** add `industry` to the `Chunk` dataclass; thread `industry: str` through
      `hybrid_search` / `dense_search` / `count` / `prune_pages` / `existing_hashes`;
      inject `WHERE industry = :industry` into both retrieval CTEs ([store.py](server/src/noscia/search/store.py)).
- [x] **Pipeline:** accept + pass `industry` through `run_search` ([search/pipeline.py](server/src/noscia/search/pipeline.py)).
- [x] **Contract:** add `industry: str = "esg"` to `SearchRequest`, `StructuredRequest`,
      `IngestRequest`, `AddSeedRequest`, `CorpusResponse` (both [contract.py](server/src/noscia/contract.py) + [api.ts](web/src/lib/api.ts)).
- [x] **Endpoints:** scope `/search`, `/structured`, `/corpus`, `/corpus/ingest`,
      `/corpus/add` by `industry`; make the in-memory search-cache key
      `(industry, query, tier)` ([app.py](server/src/noscia/app.py)).
- [x] **Ingest CLI:** `--industry <id>` (default `esg`); tag every `Chunk(industry=…)` and
      `sources.industry`; scope `--due`, prune, hashes ([ingest/run.py](server/src/noscia/ingest/run.py)).
- [x] **Recall guard:** `SET LOCAL hnsw.ef_search = 200` before both ANN queries
      ([store.py](server/src/noscia/search/store.py) `EF_SEARCH`) so the post-traversal
      `WHERE industry = …` filter doesn't starve a sparse vertical; partitioning upgrade path
      (§5.1) noted for later. *(Landed in Phase D — the 2nd vertical surfaced the real bug: a
      sparse economics filter returned **0** dense hits at the default `ef_search=40`; with 200
      it fills `top_k`. SET LOCAL keeps it transaction-scoped, never leaking onto the pool.)*
- [x] **Tests:** existing suite stays green with `industry='esg'`; scoping is proved by
      `tests/test_industry.py` (both CTEs carry the predicate; `run_search` forwards it).
      *Cross-vertical bleed is asserted structurally — the suite has no live DB.*
- [x] **Eval parity:** `train/eval.py` retrievers default to `esg`, so nDCG@10 / MRR on
      `corpus/eval/esg_queries.jsonl` is unchanged by construction (rule 9). *(The metric
      harness scores arithmetic, not a live index — full re-run is a Phase D gate.)*

### Phase A′ — source add/remove (folds in here; mostly backend) ✅ done 2026-06-15
- [x] **Store:** `delete_source(source_url, industry) -> int` (DELETE WHERE `source_url` AND
      `industry`) ([store.py](server/src/noscia/search/store.py)).
- [x] **Corpus helper:** `corpus.delete_source(url, industry)` — drop chunks + the `sources`
      row atomically ([corpus.py](server/src/noscia/corpus.py)).
- [x] **Contract:** `RemoveSeedRequest{url, industry}` / `RemoveSeedResponse{ok, removed_chunks}`
      (both sides).
- [x] **Endpoint:** `POST /corpus/remove` ([app.py](server/src/noscia/app.py)).
- [x] **Verify add path** carries `industry` (already exists via `/corpus/add`).
- [x] **Tests:** `corpus.delete_source` is `(url, industry)`-scoped and drops chunks + the
      sources row; `RemoveSeedRequest` defaults to `esg` ([tests/test_industry.py](server/tests/test_industry.py)).
- [x] **UI:** Corpus view per-row **remove** (confirm + show chunk count) and **recrawl**
      (Refresh, `/corpus/ingest {urls:[url]}`); kept the existing Add-source form ([web/src/views/Corpus.tsx](web/src/views/Corpus.tsx)).

### Phase B — industry catalog + selection (still one vertical, now selectable) ✅ done 2026-06-15
- [x] **Files:** moved `corpus/seeds.esg.yaml` → `corpus/seeds/esg.yaml` (byte-identical);
      created `corpus/industries.yaml` with the `esg` entry.
- [x] **Ingest:** `load_industries()` + `seeds_path(industry)` resolve the seed file from the
      catalog (legacy ESG path kept as fallback); `load_seeds(industry)` ([ingest/run.py](server/src/noscia/ingest/run.py)).
- [x] **User prefs:** `user_prefs(user_id, active_industry, updated_at)` table;
      `get/set_active_industry(user)` next to `current_user` ([user.py](server/src/noscia/user.py)); `corpus.industries_loaded()`.
- [x] **Contract:** `Industry{id,label,blurb,icon,active,loaded}`, `IndustriesResponse{industries,active}`, `SelectIndustryRequest{id}` (both sides).
- [x] **Endpoints:** `GET /industries`, `POST /industries/select {id}` ([app.py](server/src/noscia/app.py)).
- [x] **Tests:** catalog lists `esg` as `loaded`+`active`; selecting persists the pref ([tests/test_industry.py](server/tests/test_industry.py)).

### Phase C — onboarding UX (the setup menu + switcher) ✅ done 2026-06-15
- [x] **App state:** `activeIndustry` lifted above the Rail in [App.tsx](web/src/App.tsx); seeded
      from `GET /industries` on mount; localStorage fast-path (server pref is source of truth).
- [x] **Setup gate:** full-screen [IndustrySetup](web/src/app/IndustrySetup.tsx) when no
      loaded+active vertical — cards from `/industries` (label + blurb + icon) → `POST
      /industries/select` → if not `loaded`, build/ingest progress, then drop into search.
- [x] **Switcher:** Rail-header control showing the active label; click → same picker;
      switching clears current results (view keyed by vertical; instant when target is `loaded`).
- [x] **Plumbing:** `api.industries()` / `api.selectIndustry(id)`; [industry context](web/src/app/industry.ts)
      passes `industry` on every `search`/`structured`/corpus call; Corpus view scoped + labelled.
- [x] **Tests:** vitest [App.test.tsx](web/src/App.test.tsx) — unset/not-loaded → modal;
      loaded → straight to search; stored choice → skips gate.

### Phase D — prove it with a real second vertical ✅ done 2026-06-15
- [x] **Full v1 catalog:** authored all **9** non-ESG seed lists from
      [corpus/INDUSTRIES.md](corpus/INDUSTRIES.md) into `corpus/seeds/<id>.yaml` (economics,
      healthcare, cybersecurity, ai, energy, finance, agriculture, pharma, space) and added all
      10 entries to [industries.yaml](corpus/industries.yaml). All 10 are **selectable options**;
      only ESG ships pre-embedded — the other 9 are `loaded=false` ("builds on first use") and
      crawl **only when picked** (`/industries/select` → `/corpus/ingest`). Fixed the icon map
      (`heart`) ([web/src/app/IndustrySetup.tsx](web/src/app/IndustrySetup.tsx)).
- [x] **Crawl (test vertical):** ran Economics live via the on-pick ingest path; finalized on
      the 3 cleanly-crawled authoritative institutions — **Fed (169c), ECB (277c), BIS (65c) =
      511 chunks / 59 pages** (IMF + the other 6 sources were pruned after IMF's PDF crawl
      wedged the synchronous request; re-runnable via `--industry economics`).
- [x] **End-to-end:** Economics now `loaded=true`; the same query returns **Fed/ECB/BIS** under
      `industry=economics` vs **SEC/S&P Global ESG** under `esg` — fully disjoint, zero
      cross-vertical leak (dense + hybrid); switch back to ESG is instant (Model A).
- [x] **Eval (the honest gate):** added [corpus/eval/economics_queries.jsonl](corpus/eval/economics_queries.jsonl)
      (5 queries over the 3 indexed institutions) and made the harness multi-vertical
      (`eval --industry <id>`, [train/eval.py](server/src/noscia/train/eval.py)). Economics
      **nDCG@10 = MRR = Recall@10 = 1.000** (both tiers); ESG re-run holds at **nDCG@10=0.918 /
      MRR=0.933** (quality) — no regression from the recall guard (rule 9).
- [x] **Bugs the live run surfaced** (DB-less unit tests couldn't): `/corpus` 500 from a
      type-ambiguous `:industry IS NULL` filter (→ `CAST(:industry AS text)`); retrieved chunks
      mis-reporting `industry='esg'` (SELECT didn't hydrate the column); the recall-guard
      starvation above. All three fixed + guarded.

## 10. Why this is low-risk

- The pipeline is already vertical-agnostic; we're adding a **scope key**, not rebuilding
  retrieval.
- Every change **defaults to `esg`**, so each phase is independently shippable and the
  existing product never regresses mid-flight.
- The two genuinely new surfaces — the industry catalog and the first-run gate — are
  additive (new files, new endpoints, a new modal) and don't perturb the search path.
- The one real technical risk (filtered-ANN recall) has a cheap MVP mitigation and a clean
  partitioning upgrade that needs **no query rewrite**.
