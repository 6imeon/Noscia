# IMPLEMENTATION.md — Noscia build plan

> Companion to [SPEC.md](SPEC.md). SPEC says *what* and *why*; this file says *what's true right now* (June 2026 web research) and *the exact steps to start building*, with a phase-by-phase checklist.
> Read SPEC.md first, then this. The checklist at the bottom (§7) is the working tracker.

---

## 1. Research findings (verified June 2026)

The SPEC's stack choices were re-checked against the current landscape. **Verdict: the stack holds up — build it as written.** Notes and one or two adjustments below.

### Embedding model — confirmed, with a lighter alternative to keep in mind
- **`Qwen3-Embedding-0.6B` is still the right default.** Apache-2.0, ~0.6B params, MTEB/C-MTEB competitive at its size, 100+ languages. Loads via `sentence-transformers` (needs `>=2.7.0`) or Ollama (`ollama pull qwen3-embedding`). Native Matryoshka: truncate the 1024-dim output anywhere down to 32 and renormalize — SPEC's choice of **256 dims** is a reasonable storage/quality point.
- **New lighter option:** Google **`EmbeddingGemma-300M`** (Gemma-3-derived, multilingual, on-device-optimized). Worth a head-to-head on the ESG eval set as the "even smaller/faster" candidate, especially for a Tauri build later.
- **Bigger/API options unchanged:** Qwen3-Embedding-4B/8B locally; Voyage (voyage-3-large leads retrieval MTEB April 2026), NV-Embed-v2, Gemini Embedding via BYOK.
- **The SPEC rule stands:** pick the final model by running nDCG@10 / MRR on *our* ESG corpus, not by leaderboard. Leaderboard scores don't transfer to a narrow vertical.

### Vector store — LanceDB confirmed, less custom code than expected
- LanceDB ships **native hybrid search**: `table.search(query, query_type="hybrid")` runs vector + BM25 full-text in one store.
- **It has a built-in `RRFReranker()`** (reciprocal rank fusion) as the default fusion — so SPEC §5 step 3 (RRF) is largely free.
- It also accepts pluggable rerankers (`CrossEncoderReranker`, Cohere, etc.) for SPEC §5 step 4 — so the cross-encoder can plug into the same `.rerank()` slot instead of being wired by hand.
- **Implication:** the Phase 1 pipeline is mostly *configuration* of LanceDB's search + a custom highlight step, not a from-scratch fusion implementation.

### Reranker — `bge-reranker-v2-m3` fine, consider `Qwen3-Reranker-0.6B`
- `bge-reranker-v2-m3` (cross-encoder) remains a solid default and integrates as a LanceDB `CrossEncoderReranker`.
- Alternative to eval: **`Qwen3-Reranker-0.6B`** — pairs naturally with the Qwen3 embedder (same family/tokenizer) and is competitive. Try both in Phase 1; keep whichever wins on the eval set.

### Crawler — crawl4ai confirmed, current
- **crawl4ai v0.8.x** (v0.8.5, March 2026) is the most-used OSS crawler, MIT-licensed, Playwright/Chromium-backed, emits clean LLM-ready markdown + metadata, has built-in BM25 noise pruning. Exactly the SPEC ingestion path. Pin a v0.8.x release that is already >7 days old (§11 cooldown) and run `crawl4ai-setup` / `playwright install chromium` once.

### MUVERA + ColBERT — real, still a Phase-2 *optional*
- MUVERA (Google Research, NeurIPS 2024, arXiv:2405.19504) reduces multi-vector (ColBERT) similarity to single-vector MIPS via Fixed Dimensional Encodings — ~10% better recall at ~90% lower latency vs prior multi-vector methods, on BEIR.
- Python ref impl exists (`muvera-py`); Rust impls exist for the future Tauri hot path.
- **Keep it opt-in (SPEC §13 open question).** For a few-thousand-page vertical corpus, a *fine-tuned single-vector* model may already match it. Decide with measurement, not by default.

### pnpm 7-day cooldown — confirmed and now near-native
- **pnpm 11 turns `minimumReleaseAge` ON by default at `1440` (1 day).** SPEC raises it to **`10080` (7 days)** — correct, and now just a one-line bump over the default rather than a custom mechanism.
- `minimumReleaseAgeStrict` defaults **false** → pnpm falls back to the newest version that *is* old enough instead of failing the install (this is what makes init painless). `minimumReleaseAgeExclude` whitelists a single package for a vetted hotfix.
- **Renovate** carries the same `"minimumReleaseAge": "7 days"` across **PyPI and Cargo**, so backend + future Rust deps get parity with the frontend.
- This is a recognized supply-chain pattern (cooldowns.dev): the chalk/debug (Sept 2025) and Shai-Hulud attacks were both caught well inside a 1-day window, let alone 7.

### Desktop (Tauri 2 sidecar) — confirmed, established pattern
- Bundling a **PyInstaller-frozen FastAPI server as a Tauri 2 sidecar** that the Rust core spawns/supervises on `localhost` is a well-trodden path with multiple 2026 templates (React/Vue/Next + FastAPI). Exactly SPEC §12. Stable HTTP contract = the port stays mechanical. Defer until the web app is solid.

**Bottom line:** nothing in the SPEC needs to change to start. Two things to *evaluate* (not decide blind): EmbeddingGemma-300M vs Qwen3-0.6B, and Qwen3-Reranker-0.6B vs bge-reranker-v2-m3 — both resolved by the same on-corpus eval the SPEC already mandates.

---

## 2. Hard constraints to honor from day one

These come from SPEC §11 and the project's standing rules. Bake them in at init so they're never retrofitted:

1. **pnpm + 7-day release cooldown.** `pnpm-workspace.yaml` → `minimumReleaseAge: 10080`; `renovate.json` → `"minimumReleaseAge": "7 days"`. Commit all lockfiles. At init, if a brand-new version won't install, pin the most recent version already >7 days old — don't disable the policy.
2. **No AI attribution in git.** Plain commit messages and PR bodies — never a `Co-Authored-By: Claude` line or "Generated with Claude Code" footer.
3. **HTTP contract first.** Write `server/contract.py` and mirror it in `web/src/lib/api.ts` before implementing either side.
4. **Secrets never touch the browser, never sit in plaintext/source.** Access them through a `SecretStore` interface, never a hard-coded backend: `KeychainSecrets` (solo, via Python `keyring`) / `EnvSecrets` (the `.env` demo) / `ServerSecrets` (later). Fetched per-call; the browser only sees a masked confirmation. See §9.3.
5. **Search works without a key.** Local embeddings + local index = offline search. Only reasoning (entity search, synthetic data gen) needs BYOK.
6. **Evidence-or-null extraction.** The entity agent never emits a field it can't cite.
7. **Eval-gated model changes.** Any embedding/reranker swap is gated on nDCG@10 / MRR vs `corpus/eval/esg_queries.jsonl`.
8. **Pin versions at init** and record them in `CLAUDE.md`.

---

## 3. Prerequisites (install once)

- **Node + pnpm:** pnpm **11+** (for the native release-cooldown default). `corepack enable pnpm` or `npm i -g pnpm@latest`.
- **Python 3.11+** with a fast env manager — **`uv`** recommended (fast, hashable lockfile that pairs with the Renovate cooldown).
- **Playwright/Chromium** for crawl4ai: installed via `crawl4ai-setup` after the backend deps land.
- **Ollama** (optional but easy) for local embeddings: `ollama pull qwen3-embedding`.
- **Git** — initialize the repo; remember rule #2 (no AI attribution).

---

## 4. Step-by-step: how to begin (Phase 0, concretely)

This is the literal starting sequence. Each step maps to a checklist item in §7.

**Step 0 — repo + guardrails (do this before any app code):**
1. `git init`. Add `.gitignore` (ignore `data/`, `node_modules/`, `__pycache__/`, `.venv/`, model caches).
2. Create `pnpm-workspace.yaml` with the cooldown block (SPEC §11). Create `renovate.json` with the 7-day cross-ecosystem cooldown.
3. Create `CLAUDE.md` from SPEC §11 conventions + a "Pinned versions" table (fill as deps are added).
4. Stub `README.md`.

**Step 1 — frontend skeleton (`web/`):** *(target layout = §8 "Research Console")*
- `pnpm create vite web --template react-ts`, then `cd web && pnpm install`.
- Add Tailwind. Drop the §8.2 design tokens into `src/index.css` `:root` and reference them from `tailwind.config` (colors + fontFamily) — no hard-coded hex in components.
- Add `src/lib/api.ts` (typed client — empty stubs for now).
- Build the shell: 62px icon **Rail** + view router, and the four views as empty shells `src/views/{Search,EntitySearch,Corpus,Settings}.tsx` (see §8.3–8.4).
- Verify `pnpm dev` boots to the espresso-shell console with an empty Search split-pane.

**Step 2 — backend skeleton (`server/`):**
- Create `server/` with `pyproject.toml`; deps: `fastapi`, `uvicorn[standard]`, `keyring`, `pydantic`. Use `uv` to add + lock (respect the cooldown; pin >7-day-old versions).
- `app.py` with `GET /health` returning `{"status":"ok"}` and CORS allowing the Vite dev origin.
- Run `uvicorn server.app:app --reload`.

**Step 3 — the contract (the load-bearing step):**
- In `server/contract.py`, define Pydantic models for the Phase 1 endpoints (even if unimplemented): `/health`, `/search` (request: query, tier `fast|quality`, top_k; response: list of results with url/title/highlight/score), key-management endpoints.
- Mirror them as TypeScript types in `web/src/lib/api.ts`. **Frontend and backend types must match exactly.**

**Step 4 — wire frontend ↔ backend:**
- Frontend calls `/health` on load and shows a green/red status pill. This proves the HTTP path end-to-end.

**Step 5 — Keychain BYOK:**
- `server/secrets.py` wraps `keyring` (`set_password`/`get_password` under a `noscia` service).
- Settings view: save one key → backend stores in Keychain → read it back (return only a masked confirmation, never the raw key to the browser).

**Phase 0 DoD:** `pnpm dev` + `uvicorn` both run; `/health` is green from the browser; a BYOK key saves to Keychain and reads back. Versions recorded in `CLAUDE.md`.

---

## 5. Recommended build order after Phase 0

Follow SPEC §7 phases. The dependency spine:

```
Phase 0  skeleton + contract + keychain
   │
Phase 1  ingest(crawl→chunk→embed→LanceDB) → hybrid search → rerank → highlights → UI
   │        (LanceDB native hybrid + RRFReranker does most of the fusion)
   ├── Phase 2a  fine-tune embedder on synthetic ESG pairs (eval-gated)
   ├── Phase 2b  incremental crawl (ETag/lastmod/content_hash) + live-search fallback
   ├── Phase 2c  OPTIONAL ColBERT+MUVERA quality mode (only if eval says it earns its place)
   │
Phase 3  agentic entity search (decompose→retrieve→extract→loop→merge→cited table→CSV)
   │
Phase 4  OPTIONAL Tauri 2 desktop (PyInstaller sidecar; optional Rust hot path)
```

Build Phase 1 thin and end-to-end first (a handful of seed URLs, one query, visible highlights) before widening the corpus or adding tiers.

---

## 6. Risks / decisions to resolve early (from SPEC §13, sharpened)

- **Embedding model:** Qwen3-0.6B vs EmbeddingGemma-300M vs 4B vs API — decide on the ESG eval, not leaderboards. *Owner: Phase 1 eval harness.*
- **Reranker:** bge-reranker-v2-m3 vs Qwen3-Reranker-0.6B — same eval.
- **MUVERA/ColBERT:** measure against fine-tuned single-vector on the demo corpus before investing. Likely unnecessary at a few-thousand pages.
- **LanceDB vs Qdrant-local:** stay on LanceDB unless binary-quantization need is *measured*.
- **Name/domain clearance:** confirm `noscia` is free on npm/PyPI/crates and a domain is available **before** the name propagates through the codebase (package scopes, imports).

---

## 7. Phase checklist (working tracker)

### Phase 0 — Skeleton + guardrails
- [ ] `git init`; `.gitignore` covers `data/`, `node_modules/`, caches; **no AI attribution in commits**
- [ ] `pnpm-workspace.yaml` with `minimumReleaseAge: 10080`, `minimumReleaseAgeExclude: []`, `blockExoticSubdeps: true`
- [ ] `renovate.json` with `"minimumReleaseAge": "7 days"`, `"internalChecksFilter": "strict"`, `"automerge": false`
- [ ] `CLAUDE.md` created from SPEC §11 + pinned-versions table
- [ ] `web/` scaffolded (Vite + React + TS + Tailwind, pnpm); boots to empty search UI
- [ ] `server/` scaffolded (FastAPI + uvicorn + keyring); `GET /health` returns ok; CORS set for Vite origin
- [ ] `server/contract.py` defines Phase 1 request/response models
- [ ] `web/src/lib/api.ts` mirrors the contract types exactly
- [ ] Frontend shows live `/health` status pill (end-to-end HTTP proven)
- [ ] `server/secrets.py` exposes a `SecretStore` interface with `KeychainSecrets` + `EnvSecrets` (`.env`) impls; Settings save/read one key via it (masked on read). Ship `.env.example` with `OPENROUTER_API_KEY`
- [ ] `server/user.py` exposes a `CurrentUser` provider (`SoloUser` now; `HeaderUser` stub for later SSO) — saved-data code keys off it
- [ ] OpenRouter wired as the default provider (one key → many models); other providers selectable but optional
- [ ] *(deferred to internal-shared)* `docker-compose.yml` (web / api / embeddings-TEI / ingest) + reverse-proxy slot for Entra OIDC — **not built for the demo**, tracked in §9
- [ ] **DoD:** `pnpm dev` + `uvicorn` run; `/health` green in browser; an OpenRouter key round-trips through `SecretStore` (Keychain solo / `.env` demo)

### Phase 1 — Core ESG search
- [ ] `corpus/seeds.esg.yaml` populated with concrete ESG seed URLs grouped by `source_type` + cadence
- [ ] `ingest/crawl.py` — crawl4ai (v0.8.x, cooldown-pinned) → clean markdown + metadata; `crawl4ai-setup` run
- [ ] `ingest/chunk.py` — ~512-token chunks, ~64 overlap; compute `content_hash`
- [ ] `search/embed.py` — Qwen3-Embedding-0.6B, `search_query:`/doc prefixes, Matryoshka truncate→256→renormalize
- [ ] `search/store.py` — LanceDB table per the §4 chunk schema (dense f32[256] + BM25 sparse); upsert by `id`
- [ ] `search/hybrid.py` — LanceDB `query_type="hybrid"` + `RRFReranker()` (dense top~100 + BM25 top~100 → fuse)
- [ ] `search/rerank.py` — cross-encoder on top~50 (bge-reranker-v2-m3 **or** Qwen3-Reranker-0.6B); keep eval winner
- [ ] `search/highlight.py` — return best-matching passage(s) per result, not whole pages
- [ ] Two latency tiers: *Fast* (dense-only ANN, <200ms target) and *Quality* (hybrid+RRF+rerank, UI default)
- [ ] UI shell (§8.3): icon rail + view router + §8.2 design tokens wired into Tailwind
- [ ] UI Search view (§8.4): query box + Quality/Fast toggle → result list (badge/score/snippet) + passage reader with Highlighted↔Full-context toggle; empty/loading/error states
- [ ] UI Corpus view (§8.4): stat cards + sources table (live crawl progress) + add-seed input
- [ ] **DoD:** an ESG question returns relevant, highlighted, cited results from the local index in quality tier

### Phase 2 — Quality + freshness
- [ ] `corpus/eval/esg_queries.jsonl` held-out eval set authored
- [ ] `train/synth.py` — BYOK LLM generates ~3–5 synthetic queries per chunk
- [ ] `train/finetune.py` — fine-tune Qwen3-0.6B on the synthetic pairs
- [ ] `train/eval.py` — nDCG@10 / MRR, fine-tuned vs base; **ship only if it wins**
- [ ] Incremental crawl: sitemap `lastmod` + `ETag`/`If-Modified-Since` (304 short-circuit) + `content_hash` diff
- [ ] Adaptive recrawl cadence per source (news hourly … frameworks monthly); upsert deltas only; delete dead URLs
- [ ] Live-search fallback (BYOK Exa/Tavily/Firecrawl) when index confidence low / query out-of-corpus; merged + labeled live-vs-indexed
- [ ] *(Optional)* ColBERT + MUVERA late-interaction path behind an opt-in toggle — only if it beats fine-tuned single-vector on eval
- [ ] **DoD:** fine-tuned beats base on eval; recrawl re-embeds only changed chunks; out-of-corpus queries fall back to live

### Phase 3 — ESG entity search (showpiece)
- [ ] `agent/schema.py` — declarative company entity schema (SPEC §9), every field nullable + evidence link
- [ ] **Decompose:** LLM → extraction schema + subqueries (optional hypothetical-answer retrieval prior)
- [ ] **Retrieve:** each subquery through the Phase 1 hybrid pipeline (+ live fallback)
- [ ] **Extract:** `agent/extract.py` fills schema per entity, **explicit-evidence-only**; capture `surface_forms` + `aliases`
- [ ] **Loop:** detect gaps, issue follow-up queries until saturation or step-budget hit
- [ ] **Merge:** dedupe entities via aliases/surface forms
- [ ] **Present:** table where every cell links to its source passage; export CSV/JSON
- [ ] **DoD:** each SPEC §10 demo query returns a populated, deduped, fully-cited table

### Phase 4 — Desktop (optional, future)
- [ ] Wrap React frontend in Tauri 2 (Rust core + same web UI)
- [ ] PyInstaller-freeze FastAPI backend; Tauri spawns/supervises it as a `localhost` sidecar
- [ ] *(Optional)* port embed/store/hybrid/rerank hot path to Rust (`fastembed-rs` + `lancedb` crate)
- [ ] macOS codesign + notarize (Apple Developer ID) the bundle + sidecar binary
- [ ] **DoD:** a distributable native macOS artifact runs on a clean machine with no Python installed

---

## 8. Frontend design — "Research Console" (selected)

The chosen UI direction is **`design-1-research-console.html`** (mockup in [design/mockups/](design/mockups/)). It's a single-window, sidebar-navigated desktop console: a left icon rail switches between four views, each with a shared top search bar. This is the canonical layout to build in `web/` — the mockup is the visual + interaction reference, this section is the spec.

> The top "01 Console / 02 Cards …" switcher bar in the mockup is **gallery chrome only** — it does not ship. The app starts at the icon rail.

### 8.1 Why this direction
- **Passage-first reader, not a page list.** Results are a scannable left list; clicking one opens the full cited passage in a right reader with a **Highlighted ↔ Full-context** toggle. Matches the SPEC's "show the passage, cite the source" goal and the Exa-style research read.
- **The four SPEC views map 1:1** to the four nav items — no invented surface area. Search, Entity, Corpus & index, Settings·BYOK.
- **Provenance is always on screen:** source-type badge, rerank score bar, freshness ("● fresh"), and the live pipeline trace (`dense 112 + bm25 98 → rrf → rerank 50`) sit in the result header.
- **It's calm.** Muted espresso/terracotta, mono for metadata, sans for prose — reads like a tool, not a marketing page.

### 8.2 Design tokens (lift verbatim into Tailwind config / CSS vars)
Warm espresso shell + terracotta accent. Define these as CSS custom properties on `:root` and reference them from Tailwind's theme (`colors`, `fontFamily`) so components never hard-code hex.

```css
/* surfaces */    --bg:#201b16; --panel:#29231c; --panel-2:#241e18; --rail:#1b1611; --field:#181410;
/* lines */       --line:#3a3127; --line-2:#2a231c; --hover:#2c2419; --sel:#322617;
/* text */        --ink:#ece4d6; --muted:#a89a86; --dim:#776b5a;
/* accent */      --accent:#cc8a5c; --accent-2:#b9764a; --accent-soft:rgba(204,138,92,.14);
/* highlight */   --mark:rgba(204,138,92,.22); --mark-line:rgba(204,138,92,.6); --mark-ink:#f6ecdf;
/* status */      --ok:#92a07c; --warn:#c2a368;
/* fonts */       --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
                  --mono: "SF Mono", ui-monospace, "JetBrains Mono", Menlo, Consolas, monospace;
```

**Source-type color system (shared across the whole app — badges, dots, drawers):**

| type | token | hex | used for |
|---|---|---|---|
| framework | `--framework` | `#8b97a3` | GHG Protocol, GRI, TCFD, ISSB standards |
| regulator | `--regulator` | `#a08a9b` | IFRS/ISSB, SEC, EU CSRD |
| ratings | `--ratings` | `#c2a368` | MSCI, Sustainalytics |
| report | `--report` | `#92a07c` | company disclosures, CTAPs |
| ngo | `--ngo` | `#7f9173` | CDP, SBTi |
| news | `--news` | `#bd8a76` | ESG news wire |

Badges/borders are tinted from the base token with `color-mix(in srgb, var(--type) N%, transparent)` (10% fill / 35–40% border). Keep this table as the **single source of truth** for source-type color — backend returns the `source_type` string, frontend maps string→token.

### 8.3 Shell
```
┌────┬──────────────────────────────────────────┐
│ N  │  [ search bar ............ ] [Quality|Fast]│   ← bar is shared, per-view input/action
│ ⌕  │ ┌───────────────┬────────────────────────┐│
│ ▦  │ │ results list  │  reader (passage)       ││   ← Search view: split pane
│ ▤  │ │ (scroll)      │  scroll                 ││
│    │ └───────────────┴────────────────────────┘│
│ ⚙  │                                            │
└────┴──────────────────────────────────────────┘
 62px rail                stage (view router)
```
- **Rail** (`--rail`, 62px): logo, then Search / Entity / Corpus icons; spacer; Settings pinned to the bottom; a vertical `idx 4,182` chunk count at the very bottom. Active item = `--accent-soft` bg + accent icon. Hover tooltips (mono).
- **View router:** one `.view` section per nav item; switching toggles an `on` class. In React this is just routed views (`react-router` or a `useState` switch) — `src/views/{Search,EntitySearch,Corpus,Settings}.tsx`.

### 8.4 The four views (build order within Phase 1)
1. **Search** *(Phase 1 primary)* — top bar = query input + **Quality/Fast** segmented toggle. Split pane:
   - *List:* header showing `N passages · {tier} tier` and the live pipeline trace (dims to .35 opacity in Fast). Each result row: `#rank` · source-type badge · score bar+value · title · `org · url` (+ "● fresh" if recently crawled) · highlighted snippet (`<mark>` in `--mark`).
   - *Reader:* empty state ("select a result →"); on select shows source-type pill, title, url, a meta strip (source type / rerank score / freshness / rank), the **Highlighted ↔ Full-context** toggle, the passage (context paragraphs at 50% opacity in full mode, `<mark>` highlights), and actions (`＋ Add to entity table`, `⧉ Open source`, `⌘C Cite`).
   - *Tier behavior:* Fast re-sorts by raw score and dims the pipeline trace; Quality keeps rerank order. Wire to `/search?tier=fast|quality`.
2. **Entity** *(Phase 3)* — top bar = entity query + `Run extraction →`. Lightweight result table (company × net-zero yr × SBTi × rating × controversy), CSV/JSON export buttons, evidence-or-null. A note links to the heavier workbench concept; the console keeps the **lightweight** table. Rows open their cited passages back in the Search reader.
3. **Corpus & index** *(Phase 1)* — stat cards (chunks indexed, source pages, index size, embedding model/dims); a **Sources** table (source · type dot · pages · last crawl · cadence · status) with a live crawl **progress bar** when `status==crawling` and a `recrawl` button per row; an `＋ Add & crawl` seed-URL input. Wire to corpus/status + ingest endpoints.
4. **Settings · BYOK** *(Phase 0)* — provider cards (Anthropic / OpenAI / OpenRouter / Ollama) each with a masked key field + `save` → "● saved to Keychain" state (Ollama shows "connected · localhost:11434", no key). Default-model and default-tier chip rows. A standing note restates the **pnpm `minimumReleaseAge: 10080` cooldown**. Keys round-trip through `keyring`; the browser only ever sees a masked confirmation (§2 rule 4).

### 8.5 Component → file map (for the React build)
| mockup piece | React component | view |
|---|---|---|
| icon rail + router | `app/Rail.tsx` + view routing in `App.tsx` | shell |
| shared search bar + tier toggle | `components/SearchBar.tsx`, `components/TierToggle.tsx` | Search/Entity |
| result row | `components/ResultRow.tsx` (source badge, `ScoreBar`, snippet) | Search |
| reader pane | `components/PassageReader.tsx` (+ `ScopeToggle` highlight/full) | Search |
| source-type badge/dot | `components/SourceType.tsx` (string→token map from §8.2) | all |
| stat cards + sources table | `views/Corpus.tsx` (`StatCard`, `SourcesTable`, `CrawlProgress`) | Corpus |
| provider card | `components/ProviderCard.tsx` | Settings |
| entity table | `components/EntityTable.tsx` | Entity |

**States to build for each data surface (don't skip):** empty, loading (skeleton rows / shimmer), error (with retry), and the populated state. The mockup only shows populated — the real build owes the other three, especially for Search results and the `/health`-gated Corpus view.

The full interactive reference lives at [design/mockups/design-1-research-console.html](design/mockups/design-1-research-console.html); rationale for all five explorations is in [design/DESIGN-NOTES.md](design/DESIGN-NOTES.md).

---

## 9. Deployment targets — solo & internal-shared (Docker)

Two targets, **one codebase**, single-tenant. The HTTP-contract-first rule (§2 rule 3) is what makes this cheap — the React console only ever talks to a typed API base URL, so it doesn't care which target it's hitting.

| | **Solo** (local-first) | **Internal-shared** (the company demo) |
|---|---|---|
| Run | `uvicorn` + `pnpm dev` | `docker compose up` on an internal box (GPU if available) |
| Users | one (you) | the company, one shared index |
| Auth | none | reverse proxy → SSO (**Entra/OIDC — post-demo**; none for the demo) |
| Secrets | macOS Keychain (`keyring`) | **`.env` for the demo**; Vault / per-user later |
| Store writes | single process | `ingest` is the sole writer; `api` reads only |
| Models | in-process / native Ollama | TEI on the GPU box (batched) |

### 9.1 Demo decisions (locked)
- **Secrets = `.env`.** One org-shared set of provider keys, loaded from `.env` (gitignored; ship `.env.example`). No Vault, no per-user keys for the demo — those come later behind the same `SecretStore` interface.
- **Provider = OpenRouter.** Default reasoning provider is **OpenRouter** — one key (`OPENROUTER_API_KEY`) reaches every model, so the demo needs exactly one secret. Other providers stay selectable in Settings but aren't required.
- **No auth for the demo.** Ship behind nothing, or a basic-auth/Tailscale gate if it leaves localhost. **Entra ID (OIDC) via the reverse proxy is the planned sign-in — after the demo**, added at the proxy layer (e.g. oauth2-proxy), so the app only ever reads an identity header. No app-side auth server.

### 9.2 Compose topology (internal-shared)
```
            ┌─ reverse proxy (Caddy/Traefik) ──[ later: Entra/OIDC SSO ]─┐
  browsers ─┤  web        nginx serving the React build                  │
            │  api        FastAPI + gunicorn/uvicorn   ← reads index     │
            │  embeddings HF TEI: Qwen3-embed + reranker (GPU, batched)  │
            │  ingest     crawl4ai + Chromium — SOLE writer, sandboxed   │
            └────────────────────────────────────────────────────────────┘
   volumes:  lancedb/ (shared index, read-many/write-one)   meta-db (users, saved searches)
   env:      .env → OPENROUTER_API_KEY, model defaults, paths
```
- **TEI over Ollama** for the shared box: it batches concurrent requests and serves both the embedder and the reranker (incl. your Phase-2 fine-tuned checkpoint). Native Ollama stays fine for solo / low load.
- **Crawler as its own container** = the sandbox for untrusted web content, and the single writer to LanceDB (many concurrent readers are fine; concentrate writes).
- **Per-user data** (saved searches, collections, optional keys) → small sqlite/postgres volume, separate from the vector store.

### 9.3 Do this from Phase 0 so the shared pivot stays additive
Even building solo first, abstract the two things that differ between targets — don't thread Keychain or single-user assumptions through app code:
- **`SecretStore`** interface → `KeychainSecrets` (solo) | `EnvSecrets` (demo) | `ServerSecrets` (later). App code calls `secrets.get("openrouter")`, never `keyring` directly.
- **`CurrentUser`** provider → `SoloUser` (always "me") | `HeaderUser` (reads the SSO identity header later). Saved-data code keys off this, never assumes one user.

Everything else — the entire crawl → index → search → entity pipeline and the Research Console UI (§8) — is **identical** across both targets. Settings gains only an admin/user split (admins manage sources + keys; users search) once SSO lands.

---

## 10. Sources (June 2026)

- Qwen3-Embedding: [HF model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) · [Qwen blog](https://qwen.ai/blog?id=qwen3-embedding) · [Open embedding models guide](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models) · [MTEB leaderboard Mar 2026](https://awesomeagents.ai/leaderboards/embedding-model-leaderboard-mteb-march-2026/)
- LanceDB hybrid + rerank: [Hybrid search docs](https://docs.lancedb.com/search/hybrid-search) · [Hybrid search + custom reranking](https://www.lancedb.com/blog/hybrid-search-and-custom-reranking-with-lancedb-4c10a6a3447e)
- crawl4ai: [GitHub](https://github.com/unclecode/crawl4ai) · [Install docs v0.8.x](https://docs.crawl4ai.com/core/installation/)
- MUVERA: [arXiv 2405.19504](https://arxiv.org/abs/2405.19504) · [Google Research](https://research.google/pubs/muvera-multi-vector-retrieval-via-fixed-dimensional-encodings/) · [muvera-py](https://github.com/sionic-ai/muvera-py)
- pnpm cooldown: [pnpm supply-chain docs](https://pnpm.io/supply-chain-security) · [Socket: pnpm 11 defaults](https://socket.dev/blog/pnpm-11-adds-new-supply-chain-protection-defaults) · [cooldowns.dev](https://cooldowns.dev/)
- Tauri 2 sidecar: [Tauri embedding external binaries](https://v2.tauri.app/develop/sidecar/) · [Tauri 2 + FastAPI sidecar template](https://github.com/AlanSynn/vue-tauri-fastapi-sidecar-template)
- Frontend design (§8): mockups in [design/mockups/](design/mockups/) (selected: [design-1-research-console.html](design/mockups/design-1-research-console.html)) · rationale + UI research in [design/DESIGN-NOTES.md](design/DESIGN-NOTES.md)
