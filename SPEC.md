# SPEC.md — Noscia: a neural search app (web-first, desktop-ready)

> **Name:** Noscia (from Latin *noscere*, "to come to know"). No search/AI/RAG product or software trademark found on the name; only unrelated collisions (a film studio, a small web agency). **Before publishing, confirm directly:** the package scope is free on npm/PyPI/crates, and a domain (`noscia.app` / `noscia.dev`) is available.
> **Primary target:** Local web app — React frontend in the browser + a local backend service.
> **Future target:** macOS desktop app (Tauri shell around the same backend). See §12.
> **Demo domain:** ESG (Environmental, Social, Governance)
> **Purpose of this file:** Drop into an empty repo and hand to Claude in VS Code / Claude Code. Single source of truth for what to build and in what order. Read top to bottom before writing code.

---

## 0. What this is

Noscia is a self-contained, Exa-style neural search engine. It crawls a scoped corpus, embeds it with a (later fine-tuned) open embedding model, serves hybrid dense+sparse retrieval from an embedded vector store, reranks with a cross-encoder, and returns query-relevant highlighted passages. On top of that sits an agentic "entity search" mode that produces structured, cited tables of entities — the personal-scale equivalent of Exa Websets.

**Build it as a local web app first.** A browser can't crawl, run ML models, or host the vector store, so "web app" here means a React frontend talking over HTTP to a local backend service that does the work. That backend is the same service that a future desktop build would bundle — so going desktop later is additive, not a rewrite (§12).

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
└────────────────────────────────────────┘        │  ─ secrets via macOS Keychain (keyring)│
                                                   │                                        │
                                                   │  Embedded, on-disk, local-first:       │
                                                   │  ─ LanceDB (vector + full-text/BM25)   │
                                                   │  ─ model cache                         │
                                                   └────────────────────────────────────────┘
```

**Single tenant, two deployment targets.** The same FastAPI backend + React frontend runs either *solo* (local-first: `uvicorn` + `pnpm dev`, open `localhost`, secrets in Keychain) or *internal-shared* (one company self-hosts it via Docker Compose behind its own SSO, one shared index, secrets server-side). Either way it's single-tenant — never a hosted multi-tenant product. The HTTP-contract-first design (frontend talks only to a typed API) is what lets the same code serve both. Shared-target details live in IMPLEMENTATION §9.

**Secrets.** Abstracted behind a `SecretStore` interface so the backend never hard-codes one mechanism. Solo target → macOS Keychain via `keyring` (keys never on disk). Shared target → server secrets (`.env` for the demo; Vault / per-user encrypted store later). Keys are read per-call and never returned to the browser (masked confirmation only).

**The HTTP contract is the load-bearing decision.** Define request/response types first and keep them stable. It's what makes the desktop port (§12) a drop-in.

---

## 2. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React + TypeScript + Vite, **pnpm** | pnpm is the package manager throughout. Tailwind for styling. Runs in the browser, talks to the backend over HTTP. See §11 for the mandatory dependency release-cooldown policy. |
| Backend | Python 3.11+ + FastAPI | Runs on localhost. Owns crawl, index, search, fine-tune, and the agent loop. Served with `uvicorn`. |
| Vector store | LanceDB (embedded) | On-disk, Python bindings, native vector + full-text (BM25) search → hybrid in one store. No server to run. Alternative: Qdrant local mode if native binary quantization is wanted. |
| Crawl | `crawl4ai` | Playwright-backed, returns clean markdown + metadata. |
| Embeddings | `sentence-transformers` / Ollama | For inference and fine-tuning. See model note below. |
| Reranker | `bge-reranker-v2-m3` | Cross-encoder, run in the backend. |
| Secrets | macOS Keychain via Python `keyring` | Never write keys to disk in plaintext. |
| LLM providers (BYOK) | Anthropic, OpenAI, OpenRouter, Ollama | Pluggable provider interface (see §6). |
| **Future: desktop shell** | **Tauri 2 (Rust core + same web frontend)** | **Deferred — see §12. Optionally moves the search hot path into Rust (`fastembed-rs` + `lancedb` crate).** |

**Embedding model — current recommendation (verify at build time, the landscape moves fast):**
- **Default local:** `Qwen3-Embedding-0.6B` (open weight, Apache-2.0, strong for its size). Runs locally via Ollama or sentence-transformers. Use Matryoshka truncation to 256 dims and renormalize.
- **Bigger/better local:** `Qwen3-Embedding-4B` if hardware allows; `NVIDIA Llama-Embed-Nemotron-8B` for max multilingual quality.
- **API option:** Google Gemini Embedding (multimodal, native MRL) or Voyage v4 family, via BYOK.
- The agent must run a quick eval on **our ESG corpus** (nDCG@10 / MRR) before committing — generic leaderboard scores don't transfer, and MTEB v2 scores aren't comparable to v1.

---

## 3. Repo layout

```
noscia/
├── SPEC.md                      ← this file
├── CLAUDE.md                    ← agent working notes / conventions (create in Phase 0)
├── README.md
├── pnpm-workspace.yaml          ← pnpm config incl. release-age cooldown (§11)
├── renovate.json                ← cross-ecosystem 7-day update cooldown (§11)
├── web/                         ← React frontend (browser)
│   ├── src/App.tsx
│   ├── src/views/{Search,EntitySearch,Settings,Corpus}.tsx
│   ├── src/components/
│   ├── src/lib/api.ts           ← typed client for the backend HTTP contract
│   └── vite.config.ts
├── server/                      ← FastAPI backend (localhost)
│   ├── app.py                   ← entrypoint + route definitions
│   ├── contract.py              ← request/response models (the stable HTTP contract)
│   ├── ingest/{crawl.py,chunk.py,index.py,freshness.py}
│   ├── search/{embed.py,store.py,hybrid.py,rerank.py,highlight.py}
│   ├── train/{synth.py,finetune.py,eval.py}
│   ├── agent/{entity_search.py,schema.py,extract.py}
│   ├── providers/               ← BYOK LLM provider adapters
│   ├── secrets.py               ← keyring (Keychain) access
│   └── pyproject.toml
├── corpus/
│   ├── seeds.esg.yaml           ← ESG seed URLs + recrawl cadence
│   └── eval/esg_queries.jsonl   ← held-out eval set
├── data/                        ← LanceDB dir, model cache (gitignored)
└── src-tauri/                   ← FUTURE (§12): Tauri desktop shell. Not built until Phase 4.
```

---

## 4. Data model

**Chunk record (LanceDB row):**
```
id:            stable hash of (url + chunk_index)
url:           source URL
title:         page title
source_type:   "report" | "framework" | "regulator" | "news" | "ngo"
crawled_at:    ISO timestamp
content_hash:  hash of chunk text (for change detection)
text:          chunk text (~512 tokens, ~64 overlap)
dense:         f32[256]  (matryoshka-truncated, normalized)
sparse:        BM25 sparse vector (native LanceDB FTS)
```

**Index lifecycle:** insert/update by `id` (upsert). On recrawl, re-embed only chunks whose `content_hash` changed; delete rows for URLs no longer present.

---

## 5. The search pipeline (Phase 1 core)

Online query path:
1. Embed the query (same model, `search_query:` prefix for Qwen3, truncate→normalize).
2. **Dense prefetch** (top ~100 by cosine) + **sparse/BM25 prefetch** (top ~100) from LanceDB.
3. **Fuse** with Reciprocal Rank Fusion (RRF).
4. **Rerank** top ~50 fused candidates with `bge-reranker-v2-m3` cross-encoder.
5. **Highlights:** return the best-matching passage(s) per result, not the whole page (token-efficient, Exa-style).

**Two latency tiers** (mirror Exa Instant vs Deep):
- *Fast:* dense-only ANN, no rerank. Target < 200 ms.
- *Quality:* hybrid + RRF + cross-encoder rerank. Slower, much better. Default for the UI.

---

## 6. BYOK provider interface

One interface, four adapters. Keys live in Keychain (via `keyring`); the backend reads them at call time, never persists them elsewhere.

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
- Settings view stores at least one BYOK key in the Keychain (via `keyring`) and reads it back.
- `CLAUDE.md` created with conventions (see §11).
- **DoD:** `pnpm dev` (frontend) + `uvicorn server.app:app --reload` (backend) both run; `/health` is green from the browser; a key can be saved and retrieved.

### Phase 1 — Core ESG search
- Ingest the ESG seed list (§8) via crawl4ai → chunk → embed (Qwen3-0.6B, 256-dim) → write to LanceDB.
- Implement the §5 pipeline (hybrid + RRF + rerank + highlights) in the backend.
- UI: query box → ranked results with highlighted passages, source title/URL, fast/quality toggle.
- Corpus view: index size, last crawl time, per-source counts.
- **DoD:** a user types an ESG question and gets relevant, highlighted, cited results from the local index in the quality tier.

### Phase 2 — Quality + freshness (addresses caveats 1 & 2)
- **Fine-tune:** `train/synth.py` uses a BYOK LLM to generate ~3–5 synthetic queries per chunk; `train/finetune.py` fine-tunes Qwen3-0.6B on those pairs; `train/eval.py` reports nDCG@10 / MRR on `corpus/eval/esg_queries.jsonl` vs the base model. Ship the fine-tuned model if it wins.
- **ColBERT + MUVERA (optional quality mode):** add a late-interaction index path with MUVERA fixed-dimensional encodings so multi-vector retrieval runs through the same single-vector store. Opt-in toggle.
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

- **Pin versions at init.** FastAPI, lancedb, crawl4ai, the embedding model (and later Tauri/fastembed-rs) all move quickly. Record exact versions in `CLAUDE.md` and verify the current best small open embedding model before committing to one.
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
- **Secrets never touch disk.** Keychain via `keyring` only; the backend fetches keys per-call.
- **Search runs without a key.** Local embeddings + local index mean plain search works offline; only the reasoning model (entity search, synthetic data gen) needs BYOK.
- **Evidence-or-null in extraction.** The entity agent must never emit a field it can't cite. A blank cell beats a hallucinated one.
- **Eval before shipping a model.** Any embedding change is gated on nDCG@10/MRR against `corpus/eval/esg_queries.jsonl`.
- **Keep the corpus small and the domain narrow.** The product thesis is vertical quality, not coverage. Resist scope creep toward "search the whole web."

---

## 12. Future: desktop app (Tauri)

The web app and a macOS desktop app share the **same backend** — the difference is only the shell and how the backend is launched. Because the frontend talks to the backend over a stable HTTP contract, going desktop is additive:

- **Shell:** wrap the existing React frontend in **Tauri 2** (Rust core + the same web UI).
- **Backend launch:** instead of the user running `uvicorn`, the Rust core spawns the FastAPI backend as a **bundled sidecar** (packaged with PyInstaller) and supervises it. The frontend still calls `localhost` — no frontend change.
- **Optional speed:** port the search hot path (embed/store/hybrid/rerank) into Rust using `fastembed-rs` + the `lancedb` crate, so plain search needs no Python at runtime. The Python sidecar then only handles ingest, fine-tune, and the agent loop.
- **Distribution:** macOS **codesigning + notarization** (Apple Developer ID) for the app bundle and the bundled sidecar binary — required to run on machines other than your own. This is the main added cost of going desktop.

Do this only when you want a distributable native artifact; it is not needed for the demo.

---

## 13. Open questions to resolve early
- Final embedding model after the on-corpus eval (Qwen3-0.6B vs 4B vs an API model).
- LanceDB vs Qdrant-local once the binary-quantization need is measured against the demo corpus size.
- Whether ColBERT+MUVERA earns its place for a corpus this small, or whether fine-tuned single-vector is already enough.
- Confirm the product name and clear it (npm/PyPI/crates scope, domain, trademark) before it propagates through the codebase.

---

## 14. Non-goals
- Web-scale crawling or coverage.
- Competing with Exa/Google on breadth.
- **Multi-tenant SaaS, billing, or public sign-up.** Two deployment targets are in scope — *solo* (local-first desktop) and *internal-shared* (one company, self-hosted via Docker behind its own SSO) — never a hosted, multi-tenant, metered product. Single tenant only.
- Transmitting user keys to the browser, or storing them in plaintext / in source. (Storage backend varies by target — Keychain for solo, server secrets for shared — see IMPLEMENTATION §9.)
