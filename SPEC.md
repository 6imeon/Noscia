# SPEC.md — Noscia: a neural search app (web-first, desktop-ready)

> **Name:** Noscia (from Latin *noscere*, "to come to know"). No search/AI/RAG product or software trademark found on the name; only unrelated collisions (a film studio, a small web agency). **Before publishing, confirm directly:** the package scope is free on npm/PyPI/crates, and a domain (`noscia.app` / `noscia.dev`) is available.
> **Primary target:** Local web app — React frontend in the browser + a local backend service.
> **Future target:** macOS desktop app (Tauri shell around the same backend). See §12.
> **Demo domain:** ESG (Environmental, Social, Governance)
> **Purpose of this file:** Drop into an empty repo and hand to Claude in VS Code / Claude Code. Single source of truth for what to build and in what order. Read top to bottom before writing code.

---

## 0. What this is

Noscia is a self-contained, Exa-style neural search engine. It crawls a scoped corpus, embeds it with a (later fine-tuned) open embedding model, serves hybrid dense+sparse retrieval from **Postgres (pgvector + `pg_search` BM25)**, reranks with a cross-encoder, and returns query-relevant highlighted passages. On top of that sits an agentic "entity search" mode that produces structured, cited tables of entities — the company-internal equivalent of Exa Websets.

**It's a web app.** A browser can't crawl, run ML models, or reach the database, so "web app" here means a React frontend talking over HTTP to a backend service that does the work. The product is **company-internal**: self-hosted via Docker Compose behind the company's SSO, one shared Postgres-backed index. The same backend also runs locally (`uvicorn` + `pnpm dev`) as the development loop — see §1 and IMPLEMENTATION §9.

The whole point is **vertical, not web-scale**. We are not competing with Google or Exa on coverage. We own a bounded ESG corpus, fine-tune a small model on it, and beat a general-purpose model *inside that domain*.

### Why these choices (carry this context forward)
- A single general embedding model is the real moat for a web-scale engine. We sidestep it by going vertical and fine-tuning a small open model on synthetic ESG query/doc pairs. On a narrow corpus this beats a frontier general model.
- Late-interaction (ColBERT) retrieval beats single-vector, especially out-of-domain; MUVERA reduces multi-vector search to single-vector MIPS so we get most of that quality at single-vector speed. Optional Phase 2 quality mode, not a Phase 1 requirement.
- Freshness is solved by incremental delta-indexing (change detection + upsert), not periodic full re-crawls, plus a live-search API fallback for the long tail we don't index.
- Entity search ("find every company that…") is an agentic recursive retrieve-extract loop, not a better ranker.

---

## 1. Architecture (web-first)

```
┌─────────────── Browser ───────────────┐        ┌──────────── Local backend ────────────┐
│  Frontend (React + TS + Vite, pnpm)    │        │  FastAPI service (Python) on localhost │
│  ─ search bar, results, highlights     │  HTTP  │  ─ crawl4ai ingestion                  │
│  ─ entity-search table view            │ ◄────► │  ─ chunk + embed + index               │
│  ─ settings / BYOK key manager         │  JSON  │  ─ hybrid search + rerank + highlights  │
│  ─ corpus / index status               │        │  ─ embedding fine-tune + eval          │
│                                        │        │  ─ agentic ESG entity-search loop      │
│  Talks only to localhost:<port>        │        │  ─ LLM calls (BYOK providers)          │
└────────────────────────────────────────┘        │  ─ secrets via .env (get_secret helper)│
                                                   │                                        │
                                                   │  Backing services (Docker / local):    │
                                                   │  ─ Postgres: pgvector + pg_search BM25 │
                                                   │  ─ model cache                         │
                                                   └────────────────────────────────────────┘
```

**Single tenant, one product: a company-internal web app.** It's self-hosted via Docker Compose behind the company's own SSO, serving one shared index to that company — never a hosted, multi-tenant product. *Solo* mode (`uvicorn` + `pnpm dev` on `localhost`) is the **local development loop**, not a separate shipping target; it runs the same code against the same Postgres so dev and prod stay identical. The HTTP-contract-first design (frontend talks only to a typed API) keeps the two interchangeable. Deployment details live in IMPLEMENTATION §9.

**Secrets.** Keys are read from **`.env`** (gitignored) through a one-line `get_secret(name)` helper in `server/src/noscia/config.py` (not `secrets.py` — that shadows the Python stdlib) — app code never reads `os.environ` directly, so a later swap (per-user keys / Vault, or macOS Keychain for a hardened solo install) touches one function, not every call site. Keys are read per-call and never returned to the browser (masked confirmation only).

**The HTTP contract is the load-bearing decision.** Define request/response types first and keep them stable. It's what makes the desktop port (§12) a drop-in.

---

## 2. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React + TypeScript + Vite, **pnpm** | pnpm is the package manager throughout. Tailwind for styling. Runs in the browser, talks to the backend over HTTP. See §11 for the mandatory dependency release-cooldown policy. |
| Backend | Python 3.11+ + FastAPI | Runs on localhost. Owns crawl, index, search, fine-tune, and the agent loop. Served with `uvicorn`. |
| Datastore | **Postgres 17** + `pgvector` + `pg_search` (ParadeDB) | One datastore for everything: dense vectors (pgvector/HNSW), BM25 full-text (`pg_search`), **and** relational data — users, saved searches, SSO sessions. Hybrid = pgvector + BM25 fused with RRF in SQL. ParadeDB ships all three in one image. One container to deploy, back up, monitor. Alternative if vector scale ever dominates: a dedicated Qdrant. |
| Crawl | `crawl4ai` | Playwright-backed, returns clean markdown + metadata. |
| Embeddings | `sentence-transformers` / Ollama | For inference and fine-tuning. See model note below. |
| Reranker | `bge-reranker-v2-m3` | Cross-encoder, run in the backend. |
| Secrets | `.env` via a `get_secret()` helper | Gitignored; never returned to the browser. Keychain/Vault are later swaps behind the same helper. |
| LLM providers (BYOK) | Anthropic, OpenAI, OpenRouter, Ollama | Pluggable provider interface (see §6). |
| **Future: desktop shell** | **Tauri 2 (Rust core + same web frontend)** | **Out of scope — see §12. The product is the company-internal web app; desktop is only a possible future direction.** |

**Embedding model — current recommendation (verify at build time, the landscape moves fast):**
- **Default local:** `Qwen3-Embedding-0.6B` (open weight, Apache-2.0, strong for its size). Runs locally via Ollama or sentence-transformers. Use Matryoshka truncation to 256 dims and renormalize.
- **Bigger/better local:** `Qwen3-Embedding-4B` if hardware allows; `NVIDIA Llama-Embed-Nemotron-8B` for max multilingual quality.
- **API option:** Google Gemini Embedding (multimodal, native MRL) or Voyage v4 family, via BYOK.
- The agent must run a quick eval on **our ESG corpus** (nDCG@10 / MRR) before committing — generic leaderboard scores don't transfer, and MTEB v2 scores aren't comparable to v1.

---

## 3. Repo layout

Monorepo: a pnpm-workspace TS frontend and a uv-managed Python backend (PyPA **src-layout**, package name `noscia`). Standard hygiene — `tests/`, `ruff`, `.python-version`, CI, `.editorconfig` — is in from day one.

```
noscia/
├── SPEC.md  IMPLEMENTATION.md   ← what/why + build plan
├── CLAUDE.md                    ← agent working notes / conventions (Phase 0)
├── README.md
├── LICENSE                      ← proprietary / company-internal
├── .editorconfig
├── .github/workflows/ci.yml     ← lint + test on PR (both ecosystems)
├── package.json                 ← root workspace (private); scripts: dev / lint / test
├── pnpm-workspace.yaml          ← pnpm config incl. release-age cooldown (§11)
├── renovate.json                ← cross-ecosystem 7-day update cooldown (§11)
├── docker-compose.yml           ← Postgres (ParadeDB) for dev; full topology for deploy
├── web/                         ← React frontend (browser) — Vite + TS, pnpm
│   ├── package.json
│   ├── src/App.tsx
│   ├── src/views/{Search,EntitySearch,Settings,Corpus}.tsx
│   ├── src/components/
│   ├── src/lib/api.ts           ← typed client for the backend HTTP contract
│   └── vite.config.ts
├── server/                      ← FastAPI backend (localhost) — uv, src-layout
│   ├── pyproject.toml           ← [project] name=noscia; [tool.ruff] lint config
│   ├── .python-version          ← pins the interpreter for uv
│   ├── src/noscia/
│   │   ├── __init__.py
│   │   ├── app.py               ← entrypoint + route definitions (uvicorn noscia.app:app)
│   │   ├── contract.py          ← request/response models (the stable HTTP contract)
│   │   ├── config.py            ← get_secret() — reads .env (NOT named secrets.py: stdlib clash)
│   │   ├── user.py              ← CurrentUser provider (SoloUser | HeaderUser)
│   │   ├── ingest/{crawl.py,chunk.py,index.py,freshness.py}
│   │   ├── search/{embed.py,store.py,hybrid.py,rerank.py,highlight.py}
│   │   ├── train/{synth.py,finetune.py,eval.py}
│   │   ├── agent/{entity_search.py,schema.py,extract.py}
│   │   └── providers/           ← BYOK LLM provider adapters
│   └── tests/                   ← pytest
├── corpus/
│   ├── seeds.esg.yaml           ← ESG seed URLs + recrawl cadence
│   └── eval/esg_queries.jsonl   ← held-out eval set
├── data/                        ← Postgres volume, model cache (gitignored)
└── src-tauri/                   ← FUTURE (§12): Tauri desktop shell. Not built until Phase 4.
```

---

## 4. Data model

**Chunk record (`chunks` table in Postgres):**
```
id:            stable hash of (url + chunk_index)   — primary key
url:           source URL
title:         page title
source_type:   "report" | "framework" | "regulator" | "news" | "ngo"
crawled_at:    ISO timestamp
content_hash:  hash of chunk text (for change detection)
text:          chunk text (~512 tokens, ~64 overlap)
dense:         vector(256)   (pgvector; matryoshka-truncated, normalized; HNSW index)
               BM25 is indexed directly on `text` via a pg_search bm25 index — no stored sparse column
```

**Index lifecycle:** `INSERT … ON CONFLICT (id) DO UPDATE` (upsert). On recrawl, re-embed only chunks whose `content_hash` changed; delete rows for URLs no longer present.

---

## 5. The search pipeline (Phase 1 core)

Online query path:
1. Embed the query (same model, `search_query:` prefix for Qwen3, truncate→normalize).
2. **Dense prefetch** (top ~100 by cosine, pgvector `<=>`) + **BM25 prefetch** (top ~100, `pg_search`) — two CTEs in one Postgres query.
3. **Fuse** with Reciprocal Rank Fusion (RRF).
4. **Rerank** top ~50 fused candidates with `bge-reranker-v2-m3` cross-encoder.
5. **Highlights:** return the best-matching passage(s) per result, not the whole page (token-efficient, Exa-style).

**Two latency tiers** (mirror Exa Instant vs Deep):
- *Fast:* dense-only ANN, no rerank. Target < 200 ms.
- *Quality:* hybrid + RRF + cross-encoder rerank. Slower, much better. Default for the UI.

---

## 6. BYOK provider interface

One interface, four adapters. Keys live in `.env` (read via `get_secret()`); the backend reads them at call time, never returns them to the browser.

```python
class LLMProvider(Protocol):
    def complete(self, messages: list[dict], *, model: str, max_tokens: int) -> str: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...   # optional; local model is default
```
Adapters: `anthropic`, `openai`, `openrouter`, `ollama`. Default reasoning model is user-selectable; default embeddings are the **local** model (no key required to run search). The agentic entity-search loop (§9) needs a reasoning model — that's where a key matters.

---

## 7. Phase plan & definitions of done

### Phase 0 — Skeleton
- Scaffold `web/` (Vite + React + TS, **pnpm**) and `server/` (FastAPI). Frontend boots to an empty search UI and reaches the backend `/health` over HTTP.
- Define the HTTP contract in `server/contract.py` and mirror the types in `web/src/lib/api.ts`.
- Settings view reads at least one BYOK key from `.env` (via `get_secret()`) and shows it masked.
- `CLAUDE.md` created with conventions (see §11).
- **DoD:** `pnpm dev` (frontend) + `uvicorn noscia.app:app --reload` (backend) both run; `/health` is green from the browser; a key can be saved and retrieved.

### Phase 1 — Core ESG search
- Ingest the ESG seed list (§8) via crawl4ai → chunk → embed (Qwen3-0.6B, 256-dim) → upsert into the Postgres `chunks` table.
- Implement the §5 pipeline (hybrid + RRF + rerank + highlights) in the backend.
- UI: query box → ranked results with highlighted passages, source title/URL, fast/quality toggle.
- Corpus view: index size, last crawl time, per-source counts.
- **DoD:** a user types an ESG question and gets relevant, highlighted, cited results from the local index in the quality tier.

### Phase 2 — Quality + freshness (addresses caveats 1 & 2)
- **Fine-tune:** `train/synth.py` uses a BYOK LLM to generate ~3–5 synthetic queries per chunk; `train/finetune.py` fine-tunes Qwen3-0.6B on those pairs; `train/eval.py` reports nDCG@10 / MRR on `corpus/eval/esg_queries.jsonl` vs the base model. Ship the fine-tuned model if it wins.
- **ColBERT + MUVERA (optional quality mode):** add a late-interaction path with MUVERA fixed-dimensional encodings so multi-vector retrieval collapses to a single pgvector column — no second store. Opt-in toggle. (If multi-vector ever becomes the primary ranker, that's the point to weigh a dedicated Qdrant with native multivectors.)
- **Incremental crawl:** sitemap `lastmod` + HTTP `ETag`/`If-Modified-Since` (304 short-circuit) + `content_hash` diffing + adaptive recrawl cadence per source (news hourly, frameworks monthly). Upsert deltas only.
- **Live-search fallback:** when index confidence is low or the query is clearly outside the corpus, call a BYOK agentic search API (Exa / Tavily / Firecrawl) and merge results, clearly labeled as live vs indexed.
- **DoD:** fine-tuned model beats base on the eval set; recrawl re-embeds only changed chunks; out-of-corpus queries gracefully fall back to live search.

### Phase 3 — ESG entity search (the showpiece; addresses caveat 3)
Agentic recursive retrieve-extract loop producing a cited, structured table.
1. **Decompose:** LLM turns the entity query into an extraction schema (§9) + a set of subqueries. Optionally generate an "expected-response sketch" (hypothetical answer) to use as a retrieval prior.
2. **Retrieve:** run each subquery through the Phase 1 hybrid pipeline (and live fallback).
3. **Extract:** LLM fills the schema per candidate entity, **explicit-evidence-only** (no field without a supporting passage); capture `surface_forms` and `aliases`.
4. **Loop:** detect gaps, issue follow-up queries conditioned on what's been found, until the result set saturates or a step budget is hit.
5. **Merge:** dedupe entities via aliases/surface forms.
6. **Present:** a table where every cell links to its source passage. Export CSV/JSON.
- **DoD:** the demo queries in §10 each return a populated, deduped, fully-cited table.

### Phase 4 — Desktop app (future, optional) — see §12
Wrap the existing backend in a Tauri shell; optionally port the search hot path to Rust. Only start this once the web app is solid and you actually want a distributable native artifact.

---

## 8. ESG corpus seeds (`corpus/seeds.esg.yaml`)

Curated, not web-scale. Group by `source_type` with a recrawl cadence. Example categories (the agent should populate concrete URLs; **do not hardcode claims about the current legal/regulatory status of any framework** — treat these purely as crawl targets):

- **Frameworks / standards:** GRI, ISSB (IFRS S1 / S2), SASB, TCFD, CDP, GHG Protocol (Scope 1/2/3), CSRD / ESRS, SFDR.
- **Regulators / bodies:** relevant EU, UK, and US disclosure bodies' public pages.
- **Ratings / data:** MSCI ESG, Sustainalytics, S&P Global ESG methodology pages (methodology/explainer pages, not paywalled scores).
- **Company disclosures:** a fixed demo set of public company sustainability/annual reports (e.g. a slice of FTSE 100 issuers).
- **News / NGO:** a small set of reputable ESG news and NGO sources for the freshness/live-fallback demo.

Keep the demo corpus to a few thousand pages — enough to be convincing, small enough to crawl and fine-tune locally.

---

## 9. ESG entity schema (`agent/schema.py`)

Target entity = **company**. Default fields (all nullable, each carries an evidence link):

```
company_name
ticker / identifier
net_zero_target_year
sbti_validated            (bool)
scope1_emissions          (value + unit + reporting year)
scope2_emissions
scope3_emissions
frameworks_reported       (list: GRI / SASB / TCFD / ISSB / CSRD …)
esg_rating                (value + agency)
notable_controversies     (list, each with date + source)
board_diversity           (e.g. % women on board)
surface_forms             (list)
aliases                   (list)
```
Make the schema declarative so other entity types (funds, sectors) can be added later.

---

## 10. Demo script (what we show)

1. **Plain neural search:** *"What is the difference between Scope 2 and Scope 3 emissions?"* → highlighted passages from framework sources, with citations.
2. **Semantic over keyword:** a conceptual query that keyword search would miss (e.g. *"companies walking back climate commitments"*) → relevant results by meaning.
3. **Freshness fallback:** an event-recent query that isn't in the index → live-search results merged in, labeled.
4. **Entity search (showpiece):** *"Find FTSE 100 companies with a 2030 net-zero target and an SBTi-validated pathway, with any recent controversy"* → a populated, deduped, fully-cited table; export to CSV.

---

## 11. Conventions (put in `CLAUDE.md`)

- **Pin versions at init.** FastAPI, pgvector/`pg_search` (ParadeDB), crawl4ai, the embedding model all move quickly. Record exact versions in `CLAUDE.md` and verify the current best small open embedding model before committing to one.
- **pnpm everywhere on the JS side.** Use pnpm, not npm or yarn. Commit `pnpm-lock.yaml`.
- **7-day dependency release cooldown (mandatory, supply-chain defense).** Newly published package versions must be at least 7 days old before they can be installed. Most malicious releases (account hijacks, typosquats, poisoned patches) are detected and yanked within hours, so a 7-day delay puts the build outside the attacker's window at zero cost. Enforced in two layers:
  - **pnpm** (native, covers the npm ecosystem) — in `pnpm-workspace.yaml`. `minimumReleaseAge` is in **minutes**; 7 days = `10080`. pnpm 11 already defaults this to `1440` (1 day); we raise it.
    ```yaml
    # pnpm-workspace.yaml
    pnpm:
      minimumReleaseAge: 10080          # 7 days, in minutes
      minimumReleaseAgeExclude: []      # add a package here ONLY for an urgent vetted security patch
      blockExoticSubdeps: true          # no git/tarball transitive sources
    ```
  - **Renovate** (cross-ecosystem, covers npm **and** PyPI **and** Cargo) — in `renovate.json`, so the Python backend and any future Rust deps get the same cooldown that pnpm gives the frontend.
    ```json
    {
      "extends": ["config:recommended"],
      "minimumReleaseAge": "7 days",
      "internalChecksFilter": "strict",
      "automerge": false
    }
    ```
  - **Never auto-merge a fresh release.** Lockfiles (`pnpm-lock.yaml`, `uv.lock`/hashed requirements, and later `Cargo.lock`) are committed and treated as the trusted base. Emergency security fixes bypass the cooldown only via an explicit, reviewed exclude entry — never by disabling the policy globally.
  - *Note:* the cooldown can make a brand-new version temporarily un-installable, most noticeably at project init. That's the policy working — pin to the most recent version already older than 7 days rather than excluding it.
- **HTTP contract first.** Define `server/contract.py` ⇄ `web/src/lib/api.ts` before implementing either side. This is what keeps the desktop port (§12) mechanical.
- **Secrets never touch the browser.** Read from `.env` via `get_secret()`; `.env` is gitignored; the backend fetches keys per-call and only ever returns a masked confirmation.
- **Search runs without a key.** Local embeddings + local index mean plain search works offline; only the reasoning model (entity search, synthetic data gen) needs BYOK.
- **Evidence-or-null in extraction.** The entity agent must never emit a field it can't cite. A blank cell beats a hallucinated one.
- **Eval before shipping a model.** Any embedding change is gated on nDCG@10/MRR against `corpus/eval/esg_queries.jsonl`.
- **Keep the corpus small and the domain narrow.** The product thesis is vertical quality, not coverage. Resist scope creep toward "search the whole web."

---

## 12. Future: desktop app (Tauri)

The web app and a macOS desktop app share the **same backend** — the difference is only the shell and how the backend is launched. Because the frontend talks to the backend over a stable HTTP contract, going desktop is additive:

- **Shell:** wrap the existing React frontend in **Tauri 2** (Rust core + the same web UI).
- **Backend launch:** instead of the user running `uvicorn`, the Rust core spawns the FastAPI backend as a **bundled sidecar** (packaged with PyInstaller) and supervises it. The frontend still calls `localhost` — no frontend change.
- **Distribution:** macOS **codesigning + notarization** (Apple Developer ID) for the app bundle and the bundled sidecar binary. This is the main added cost of going desktop.

**Status: out of scope.** The product is the company-internal web app (§1); desktop is not a current target, and Postgres being a server (not an embeddable file store) makes a bundled single-binary desktop build more involved than it was under the old embedded-store plan. Kept here only as a possible future direction.

---

## 13. Open questions to resolve early
- Final embedding model after the on-corpus eval (Qwen3-0.6B vs 4B vs an API model).
- Whether Postgres (pgvector + `pg_search`) holds up at the company's corpus size, or a dedicated vector engine (Qdrant) is eventually warranted — decided by measured QPS/recall, not upfront.
- Whether ColBERT+MUVERA earns its place for a corpus this small, or whether fine-tuned single-vector is already enough.
- Confirm the product name and clear it (npm/PyPI/crates scope, domain, trademark) before it propagates through the codebase.

---

## 14. Non-goals
- Web-scale crawling or coverage.
- Competing with Exa/Google on breadth.
- **Multi-tenant SaaS, billing, or public sign-up.** The product is **one company-internal app**, self-hosted via Docker behind that company's own SSO — never a hosted, multi-tenant, metered product. Single tenant only. (*Solo* `uvicorn`+`pnpm dev` is the dev loop, not a separate target.)
- Transmitting user keys to the browser, or committing them to source. (Keys live in a gitignored `.env`, read via `get_secret()`; a hardened backend — Keychain / Vault — is a later swap behind that one helper. See IMPLEMENTATION §9.)
