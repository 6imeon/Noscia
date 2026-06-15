# Changelog

All notable changes to Noscia are recorded here. Updated at the **end of each phase**
(see [IMPLEMENTATION.md](IMPLEMENTATION.md) §7). Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); dates are absolute.

## Landing page — fluid hero + marketing sections — 2026-06-15

A public marketing page at **`/landing`**, in Noscia's own visual language (Oat palette,
system sans + SF Mono, caramel accent). Five hero directions were built as standalone
prototypes and rendered/screenshotted headlessly; the chosen "aurora" direction was ported
into React.

### Fluid particle hero (`web/src/views/Landing.tsx`)
- The hero is a field of free-floating gradient blobs that the cursor repels like a fluid.
  Grounded in Jos Stam's *Stable Fluids* (force, advect, diffuse): repulsion is a smooth
  outward **force** added to each particle's own velocity (no positional tether), with a
  viscous drag back to a baseline drift. Modeled as many small particles (SPH-style) so the
  cursor displaces only the **local** ones, so the field parts and flows back instead of a
  single blob snapping 180°. Honors `prefers-reduced-motion`.
- Routed by path in `main.tsx`: the console stays at `/`, the landing renders at `/landing`,
  with no router dependency added.

### Content sections
- "What it does" cards, a plain-language search showcase with a cited-results product mock,
  and a closing CTA, on the warm palette with sage-green accents. Scroll-reveal via
  `IntersectionObserver` plus light scroll parallax; entrance and reveal animations live in
  `web/src/styles/theme.css`.

### Removed
- An earlier experiment streamed a third-party hosted background video (external egress,
  choppy playback). It and its 30 MB asset were dropped in favor of the self-contained
  particle hero.

### Gates
- Web: `tsc` typecheck clean. The landing is presentational; no contract or API surface
  changed, so the server tests and the eval gate are unaffected.

## Phase D — Full vertical catalog + second live corpus — 2026-06-15

The multi-industry feature is proven end-to-end: ten selectable verticals, embeddings
strictly on-pick, and a real second corpus (Economics) that searches in isolation from ESG.

### Ten verticals, embedded on demand (`corpus/seeds/`, `corpus/industries.yaml`)
- Authored the 9 non-ESG seed lists from `corpus/INDUSTRIES.md` (economics, healthcare,
  cybersecurity, ai, energy, finance, agriculture, pharma, space) and registered all 10 in
  the catalog. Every vertical is a **selectable option**, but only ESG ships pre-embedded —
  the other 9 are `loaded=false` ("builds on first use") and crawl **only when picked**
  (`/industries/select` → `/corpus/ingest`). Nothing is pre-crawled. Fixed the picker icon
  map (`heart`).

### Economics: the live second corpus (`corpus/eval/economics_queries.jsonl`)
- Crawled Economics via the on-pick ingest path and finalized on 3 cleanly-indexed
  authoritative institutions — **Fed (169c), ECB (277c), BIS (65c) = 511 chunks / 59 pages**.
  (IMF's PDF crawl wedged the synchronous request; it and the remaining sources were pruned
  and are re-runnable via `--industry economics`.)
- **Switch proven**: one query returns Fed/ECB/BIS under `industry=economics` vs SEC/S&P
  Global ESG under `esg` — fully disjoint, zero cross-vertical leak (dense + hybrid). Switch
  back to ESG is instant (Model A).
- **Eval** (rule 9): the harness is now multi-vertical (`eval --industry <id>`). Economics
  scores **nDCG@10 = MRR = Recall@10 = 1.000** (both tiers); ESG re-run holds at
  **nDCG@10=0.918 / MRR=0.933** (quality) — unchanged by the recall guard below.

### Bugs the live run surfaced (the DB-less unit tests could not)
- **`/corpus` 500 for every user** — Phase A's `(:industry IS NULL OR …)` filter was
  type-ambiguous in Postgres (`AmbiguousParameter`). Fixed with `CAST(:industry AS text)`
  (the `::text` shorthand mis-parses under SQLAlchemy `text()`); added a regression guard.
- **Retrieved chunks mis-reported `industry='esg'`** — `_row_to_hit` never hydrated the
  column. Added `industry` to both retrieval SELECTs + the `Chunk` reconstruction.
- **Filtered-ANN recall starvation** (the deferred Phase A guard, landed here) — a sparse
  vertical returned **0** dense hits because HNSW's default `ef_search=40` < `PREFETCH` and
  the `industry` filter applies after the index traversal. Added `SET LOCAL hnsw.ef_search =
  200` before both ANN queries (transaction-scoped, never leaks onto the pooled connection);
  economics now fills `top_k` where it returned 0.

### Gates
- Server: `ruff` clean, **88 pytest** (added catalog-completeness, CAST-regression, and
  recall-guard guards; the multi-vertical eval was validated live). Web: lint + build + 3
  vitest green.

## Phase C — Onboarding UX (setup menu + switcher) — 2026-06-15

The vertical is now chosen **in the UI**: a first-run setup menu, a header switcher, and
every search/extract/corpus call carries the active vertical.

### Setup gate + switcher (`app/IndustrySetup.tsx`, `app/industry.ts`, `App.tsx`)
- `App` resolves the active vertical from `GET /industries` on mount: a loaded+active
  vertical boots straight to search; an unchosen / not-yet-built one shows a full-screen
  **setup menu** (cards: label · blurb · icon · `ready`/`builds on first use`). A returning
  user's `localStorage` choice skips the gate (server pref stays source of truth); a missing
  catalog degrades to the app rather than trapping the user behind the gate.
- Picking a vertical → `POST /industries/select`; if it isn't `loaded`, a **“building
  corpus”** state runs the first ingest (`POST /corpus/ingest {industry}`) before entering.
  Already-loaded verticals switch **instantly** (Model A — no recrawl).
- Rail-header **switcher** (active label ▾) re-opens the same picker; the view container is
  keyed by the active vertical so switching clears stale results/corpus rows.

### Active vertical threaded through every call (`app/industry.ts` context)
- New `IndustryProvider` / `useIndustry()` — Search, Structured, and Corpus read the active
  vertical from context (no prop-drilling through the OutputPane tab chrome) and send
  `industry` on `search` / `structured` / `corpus` / `ingest` / `add` / `remove`.
  `api.corpus(industry)` now scopes the Corpus view, which shows the active vertical's label.
- Tests (`App.test.tsx`): loaded+active → straight to search; not-loaded active → gate;
  stored choice → skips gate. Web gate green (3 vitest); Python unchanged (85).

## Phase B — Industry catalog & selection — 2026-06-15

The vertical becomes **chosen, not compiled in**. Still one corpus (ESG), but now
selectable end-to-end through a real catalog + per-user preference. No UX yet (Phase C).

### Catalog as checked-in config (`corpus/`)
- `corpus/seeds.esg.yaml` → **`corpus/seeds/esg.yaml`** (byte-identical move; the seed
  schema is unchanged). New **`corpus/industries.yaml`** — the catalog: `{id, label, blurb,
  icon, seeds}` per vertical (just `esg` today; the 10-vertical v1 list waits in
  [corpus/INDUSTRIES.md](corpus/INDUSTRIES.md)). Industries are static content, not a DB table.
- `ingest/run.py`: `load_industries()` reads the catalog; `seeds_path(industry)` resolves a
  vertical's seed file from it (legacy ESG path kept as a fallback so a missing catalog never
  breaks ingest); `load_seeds(industry)` reads the resolved file.

### Per-user active vertical (`db/`, `user.py`, `corpus.py`)
- New `user_prefs(user_id, active_industry, updated_at)` table (idempotent). "Loaded one at a
  time" is **this row**, not a physical data swap — switching never recrawls (Model A).
- `user.py`: `get_active_industry(user)` / `set_active_industry(user, id)` next to
  `current_user` — keyed by `User.id` (`solo` today; SSO-swappable with no call-site change).
  `corpus.industries_loaded()` → the verticals that have crawled sources (the `loaded` flag).

### Endpoints + contract (`app.py`, `contract.py` ⇄ `web/src/lib/api.ts`)
- `GET /industries` → the catalog ⨯ this user's state (each entry `active`/`loaded`).
  `POST /industries/select {id}` → validates against the catalog (404 otherwise), persists the
  pref, returns the refreshed catalog. New `Industry` / `IndustriesResponse` /
  `SelectIndustryRequest` models, mirrored in `api.ts` with `api.industries()` /
  `api.selectIndustry(id)`.
- Tests (`tests/test_industry.py`): catalog lists `esg` with its seed file; `seeds_path`
  resolves to the relocated file and rejects unknown ids; `/industries` marks the active+loaded
  vertical; select validates (404) and persists. Full suite green (85 py); web gate green.

## Phase A + A′ — Multi-industry backend scoping & source removal — 2026-06-15

Groundwork for **multi-vertical** Noscia (design: [MULTI_INDUSTRY.md](MULTI_INDUSTRY.md)):
the corpus stops being hard-wired ESG. This phase is **invisible** — every change
defaults to `industry = 'esg'`, so the app behaves exactly as before until a second
vertical is added (Model A: all verticals coexist, "loaded" = the active filter).

### Scope key end-to-end (`db/`, `search/store.py`, `search/pipeline.py`)
- `chunks.industry` / `sources.industry` — `TEXT NOT NULL DEFAULT 'esg'` (idempotent
  `ADD COLUMN`; the default *is* the migration — every existing row becomes ESG with no
  data move), each with a btree index — the seam the `PARTITION BY LIST` upgrade builds on.
- `VectorStore` threads `industry` through `upsert` / `hybrid_search` / `dense_search` /
  `count` / `prune_pages` / `existing_hashes`; **both** retrieval CTEs (dense + BM25) now
  filter `WHERE industry = :industry`, so a search never crosses verticals. `Chunk` gains
  `industry` (defaults `'esg'`). `run_search` forwards `req.industry`.

### Contract + ingest (`contract.py` ⇄ `web/src/lib/api.ts`, `ingest/run.py`)
- `industry` added to `SearchRequest` / `StructuredRequest` / `IngestRequest` /
  `AddSeedRequest` / `CorpusResponse` (both sides, rule 5; defaults `'esg'`).
- Ingest CLI gains `--industry <id>`; every `Chunk` and `sources` row is tagged; `--due`,
  prune, and hash-diff are vertical-scoped. Phase A keeps the single `seeds.esg.yaml`
  (per-industry seed files land in Phase B). The in-memory search cache key became
  `(industry, query, tier)`.
- Eval parity holds: `train/eval.py` retrievers default to `'esg'`, so rule 9's
  nDCG@10/MRR gate scores the ESG vertical exactly as before.

### Source add **and** remove (`store.py`, `corpus.py`, `app.py`, `views/Corpus.tsx`)
- New `POST /corpus/remove` (`RemoveSeedRequest`/`RemoveSeedResponse`): `delete_source`
  drops every chunk discovered under a seed (seed page + all deep-crawled pages, matched
  by `source_url`) **and** its `sources` row, atomically and industry-scoped.
- Corpus view: each source row gains **remove** (confirms the chunk count it will drop —
  re-adding re-pays the crawl) alongside the existing **recrawl** (Refresh). Add-source
  form unchanged; it now tags the active vertical.

### Tests
- New `tests/test_industry.py` (no DB/models): both hybrid legs + the dense leg carry the
  scope predicate; `run_search` forwards `industry` and defaults it to `'esg'`;
  `corpus.delete_source` is `(url, industry)`-scoped and drops chunks + the sources row;
  every industry-carrying contract model defaults to `'esg'`. Full suite green (79 py);
  web lint/tsc/vitest/build green.

## Phase 2.5 — Corpus depth (deep crawl) — 2026-06-14

The index went from **8 single landing pages** to a professional-scale corpus by
crawling each authoritative domain in *depth* — never the open web (rule 13). A seed is
now a **site section**, not one page.

### Deep crawl (`server/src/noscia/ingest/`)
- `crawl.py::crawl_site` — bounded **same-domain BFS** (crawl4ai `BFSDeepCrawlStrategy`):
  `max_depth` / `max_pages` per seed, `include_external=False`, non-HTML dropped by
  content type, and a junk-path exclude list (login/search/taxonomy/legal/nav). crawl4ai's
  memory-adaptive dispatcher throttles concurrency so it stays inside the 18 GB box.
- `run.py` restructured to **per-seed** ingestion: each seed deep-crawls → every page is
  hash-diffed independently → a **source-level page prune** drops chunks whose page vanished
  from the site. Single-page seeds (`max_depth: 0`) keep the cheap 304 short-circuit; deep
  seeds always crawl (a landing-page 304 says nothing about sub-pages) and lean on the diff.
- `chunks.source_url` (idempotent `ALTER`) ties every chunk back to the seed it was found
  under — the key that makes source-level page pruning and accurate per-source page counts work.
- `seeds.esg.yaml` — expanded from 8 → **21 authoritative ESG domains** (frameworks,
  regulators, ratings, NGOs, news), each with a `crawl:` block (depth/page caps/excludes)
  tuned to a ~300–500-page index. Still curated and narrow (rule 11): depth, not breadth-to-the-web.

### Content quality — clean prose, not page chrome (`crawl.py`, `chunk.py`)
- Default crawl4ai output is *raw* markdown — on these sites dominated by cookie banners,
  cookie-declaration tables, language/nav menus. Fixed in three layers: a `PruningContentFilter`
  (density heuristic → populates `fit_markdown`), `excluded_tags` (nav/header/footer/aside/form),
  and `excluded_selector` dropping the consent widgets (Cookiebot/OneTrust) **at the source** —
  plus a chunk-level line filter for stray banner sentences that keeps real ESG terms (FPIC —
  Free, Prior and Informed *Consent*). Verified **0 cookie-polluted chunks** across the corpus.
- Tested and rejected `remove_overlay_elements` / JS "Accept all" click: the former deletes
  ghgprotocol.org's main content (misreads it as an overlay); the latter dismisses the *popup*
  but leaves Cookiebot's inline *declaration table* in the DOM (GRI: 40 cookie mentions remain).
  Removing the widget by selector is strictly cleaner.

### Eval re-grounded to source-domain level (`train/eval.py`)
- Relevance is now judged at the **source domain**, not the exact URL: a query names the
  authoritative org that answers it, and any page of that domain counts (deduped to its best
  rank per domain). Deep-crawl sub-pages and recrawl URL churn no longer perturb rule 9's gate.
  The existing `esg_queries.jsonl` labels stayed valid by construction (domains unchanged).
- **Corpus at end of phase 2.5: 581 pages / 4,817 chunks across 21 sources** (8 → 21 domains;
  41 MB index) — includes the PDF documents (reflowed to prose) and URL-deduplication below.
  Eval **Quality** nDCG@10 0.918 · MRR 0.933 · Recall@10 0.911; **Fast** 0.881 · 0.900 · 0.911.
  The gate **de-saturated** (was ≈0.99/1.000 on the 8-doc corpus) — there's now measurable
  headroom, so a fine-tune *could* show a win and rule 9 can discriminate again.

### PDF extraction — the substance HTML crawling misses (`ingest/pdf.py`, `pypdf` 6.13.0)
- Some authoritative domains publish their real content as **PDFs**, not HTML — TCFD's
  recommendations + annual status reports are the clearest case (the site was 1 thin page).
  `crawl_site` now harvests PDF links found across the crawled pages and `extract_pdf` fetches
  each (`httpx`, size-capped, fail-soft) and pulls its text with `pypdf` — flowing through the
  **same** chunk → embed → upsert path as HTML, citing its own URL.
- Kept **curated**, not open-web (rule 11/13): PDFs are taken from the seed's own domain plus
  an explicit per-seed `pdf_hosts` allow-list (e.g. TCFD's `assets.bbhub.io` publications CDN).
  A per-seed `max_pdfs` cap and translation excludes keep the budget on English originals.
  Scanned/image-only PDFs (no text layer) and oversized files are skipped, never OCR'd.
- One subtlety worth recording: the deep-crawl run config dropped *external* links before
  discovery could see them, so an allow-listed external host (`assets.bbhub.io`) was invisible
  even though same-domain PDFs worked. Fixed by keeping external links in `result.links`
  (markdown stays link-free via the generator; BFS scope is still bounded by `include_external`).
  Net: **44 PDF documents / 2,205 chunks** indexed — TCFD went from 1 thin landing page to its
  full 2017 recommendations report.

### URL canonicalization — no more `?page=1` duplicate results (`ingest/url.py`)
- A deep crawl surfaced the same page under cosmetic variants (`?page=1` ≡ the bare URL,
  trailing slash, `#fragment`, `utm_*` tracking) — each minting a distinct `chunk_id` and a
  **duplicate search result**. `canonical_url` folds them at the single point a crawled page
  gets its URL: lowercase host, drop fragment + tracking + first-page pagination, strip trailing
  slash, sort surviving params. Conservative — `?page=2` and unknown params are preserved.
  After re-ingest the corpus holds **0** `?page=1`/`?paged=1` duplicate result URLs (was 64).
- Follow-up: the `_gl` / `_gac` / `_gcl_*` Google-Analytics linker family leaked into Ceres
  and Sustainalytics PDF citation URLs (it isn't `utm_*`); added it to the strip list.

### Result readability — clean PDF prose + an Exa-style answer layer
- `pypdf` emits *layout-faithful* text: a page's columns, wrapped lines and table rows
  all arrive split by `\n`, so PDF passages read as fragmented soup and the
  sentence-window highlighter couldn't form a clean excerpt (it hard-truncated with `…`).
  `pdf.py::_clean_pdf_text` reflows it to prose — rejoin soft-wrapped lines, keep
  paragraph breaks, keep hyphens at wraps (ESG is dense with real compounds like
  *climate-related*; merging them would be worse than the rare syllable artifact). The
  highlighter also now treats hard line breaks as sentence boundaries.
- **Synthesized answer (`search/summarize.py`)** — an opt-in, BYOK answer layer in the
  spirit of Exa's/Perplexity's answer: a *single* LLM call over the top passages
  synthesizes one direct, 2–4 sentence answer to the query, with inline `[n]` citations
  back to the result rows it used. One answer over all top passages (not per-result), so
  an answer split across several rows still comes together — and the user sees it once, up
  top, instead of hunting for the row that happens to contain it. Grounded, never freelance
  (rule 8): answers only from the retrieved passages, returns `NONE` (→ null, shown as an
  honest "no direct answer in the corpus") when they don't contain it. BYOK via `get_secret`
  (no key ⇒ no answer, no error). Contract grew `SearchRequest.summarize` +
  `SearchResponse.answer` / `answer_citations` / `summarized`; the UI adds a key-gated
  **✦ AI answers** toggle (on by default when a key is present). The right pane is split:
  the synthesized answer sits on top (its `[n]` chips open the cited source), the clicked
  source passage reads below — answer always in view, evidence on demand.
- **Model pre-warm (`app.py` lifespan)** — the embedder + cross-encoder are lazy +
  `lru_cache`'d, so the *first* search used to pay the full ≈1 GB cold-start (minutes on
  CPU). A daemon thread now loads them at boot (off the request path; boot stays instant,
  skipped under pytest) so the first search is as fast as the rest. Remaining latency is
  pure inference: warm, fast tier ≈1 s / quality ≈9 s on host MPS, vs ≈4 s / ≈52 s in the
  CPU-only Docker container (Docker on macOS can't reach Metal) — for a snappy dev loop run
  the API natively on the host (`docker compose up postgres` + host `uvicorn`).

### Recency — publication dates + a news-weighted ranking prior (`search/recency.py`)
- The index recorded only `crawled_at` (when *we* fetched a page), never when the document
  was *published* — so ranking couldn't tell a 2024 piece from a 2017 one, and the UI
  surfaced near-decade-old sources with no date shown. Two parts fix that:
- **Publication-date extraction at ingest.** `crawl.py` reads the `<head>` meta
  (`article:published_time` / `og:published_time` / Dublin Core / `citation_*` / JSON-LD
  `datePublished`, priority-ordered) and `pdf.py` reads the PDF `/CreationDate` (the
  document date HTML crawling can't see — e.g. the TCFD reports). Both parse to a tz-aware
  UTC date through a sanity window (1990…now+1y), and are strictly **evidence-or-null**
  (rule 8): an unparseable or absent date stays `NULL`, never guessed. Stored in a new
  nullable `chunks.published_at` (idempotent `ALTER`); because publication date is
  *page-level*, `store.stamp_published_at` backfills every chunk of a page so an
  *incremental* recrawl dates even content the hash-diff left untouched.
- **News-weighted recency prior.** `apply_recency_prior` (post-rerank, mirrored in the eval
  retrievers) nudges results by a bounded, **boost-only** multiplier — applied **only** to
  the `news` source_type, decaying with a 180-day half-life. Evergreen standards are never
  touched (TCFD 2017 is still canonical; age ≠ staleness), un-dated chunks are a no-op, and
  nothing is ever demoted below its relevance baseline.
- **Eval-gated to 0.05 (rule 9).** A first pass at `MAX_BOOST=0.15` *regressed* the gate
  (Quality nDCG@10 0.918→0.893): a same-day esgtoday article on the new SBTi net-zero
  standard leapfrogged SBTi's own authoritative page (q10). A sweep showed parity holds
  through 0.08 and breaks at 0.10, so the prior ships at **0.05** — a true tie-break (can
  only reorder items already within 5% relevance, never override a clear winner). Eval at
  0.05 is byte-identical to baseline: Quality **nDCG@10 0.918 / MRR 0.933 / Recall@10
  0.911**, Fast **0.884 / 0.900 / 0.911**. Note: the eval set is framework-centric, so the
  gate proves *no regression* but cannot yet measure the prior's *benefit* on time-sensitive
  news queries — adding news-relevance eval queries is the honest next gate.
- **UI** surfaces the date: a compact year on each result row (full date on hover) and a
  `published · YYYY-MM-DD` field in the passage reader. `SearchResult.published_at` added to
  the contract + TS mirror.

### Structured extraction — the answer as cited JSON (`search/structured.py`, `/structured`)
- A second output tab beside the prose answer (cf. Exa's Answer / Structured): same grounded
  retrieval, but the model returns the answer as a **flat JSON object** — snake_case keys
  naming the salient aspects of the query, each `value` one self-contained synthesized
  sentence, each carrying the source rows it drew on. One BYOK call constrained by an
  OpenAI/OpenRouter **Structured-Outputs** JSON schema over the same top passages the answer
  uses, so a structured pull costs no extra retrieval — just one synthesis.
- **Two modes, one contract.** AUTO (default, empty `fields`): the model derives the fields
  from the query so the tab mirrors the answer instead of forcing a fixed schema that comes
  back all-blank when it doesn't fit the question. MANUAL (pinned `fields`): the caller fixes
  a schema (build-a-table use case), slugged into a strict per-field object. Both are
  **evidence-or-null** (rule 8): an unsupported field/value is `null`, uncited — never guessed.
  No key ⇒ all-null, no error.
- **Auto-runs once per query** when the tab is first opened (no click), and the result is
  cached across tab switches so a paid call never re-fires on a flip; MANUAL waits for an
  explicit Extract so field edits don't fire a call per keystroke.
- **No re-running the pipeline.** `/structured` reuses the just-run retrieval via a small
  in-process last-search cache keyed by (query, tier) — answer-free deep-copy snapshots, so a
  cached entry can't leak a stale synthesized answer. Cut the Structured latency from re-doing
  embed+rerank (≈1 min in the CPU-only container) to the single LLM call (~4–5 s).
- Contract grew `StructuredField` / `StructuredRequest` / `ExtractedField` / `StructuredResponse`
  (`contract.py` ⇄ `web/src/lib/api.ts`, matched). Frontend: `OutputPane` tabs (✦ Answer /
  ⊞ Structured), `StructuredPanel` (JSON-object render, `null` for blanks, collapsible field
  editor + ESG preset), and shared citation primitives extracted to `Citations.tsx`
  (`CitedText` for the answer's inline `[n]`, `CiteHosts` for the structured values' Exa-style
  `host +N` chips, `Sources` list) so both tabs render provenance identically.

### Visual identity — light "Oat" theme + the Neural-N mark
- **Theme flipped dark → light.** The `@theme` tokens in `index.css` moved from the espresso
  shell to a warm off-white **"Oat"** nude palette (dark ink on warm paper). Components still
  read only tokens — no hard-coded hex (the day-one rule) — so the flip was a token swap plus
  one new `--color-on-accent` for text on filled accent buttons (the three active toggles that
  had assumed a dark page background are now legible on the light surface).
- **Neural-N logo + favicon.** A node-edge "N" graph (four corner nodes + a center hub):
  `app/Logo.tsx` is the themed in-app mark (reads `--color-accent` / `--color-ink`), and
  `public/favicon.svg` is the dark app-icon tile (replacing the stock Vite mark). Explorations
  kept under `design/mockups/` (5 light palettes, 10 logo concepts).

### Cite action — real copy, honest label (`PassageReader.tsx`)
- The reader's Cite button copied `"{title} — {url}"` to the clipboard but gave **no
  feedback** and was labelled `⌘C` for a shortcut that was never wired. Now it confirms
  (**✓ Copied**, reverts after 1.5 s), fails soft when the clipboard is blocked, and drops the
  misleading `⌘C` prefix (→ **❝ Cite**, with its own glyph so it's not a twin of ⧉ Open source).

## Phase 2 — Quality + freshness — 2026-06-14

Two halves landed: an **eval gate** for every model change, and **incremental
freshness** so recrawls are cheap. The fine-tune pipeline is built, runs locally on
an 18 GB machine, and is **honestly eval-gated** — it does not ship because the demo
corpus is too small for the eval to show a win (see note). Search stays **index-only**:
no third-party search providers, no external data egress (rule 13).

### Eval harness (`server/src/noscia/train/eval.py`)
- `corpus/eval/esg_queries.jsonl` — 15 held-out ESG queries with **URL-level relevance**
  grounded in the actually-indexed text (no query sees its own training signal).
- nDCG@10 / MRR / Recall@10 over a deduped URL ranking; a *retriever* is just
  `(query, k) → ranked URLs`, so base-vs-fine-tuned compare on the same set/metrics.
  Built-in retrievers wrap the live Quality + Fast tiers. `--per-query` breakdown.
- **Honest finding:** on the 8-doc demo corpus retrieval is near-saturated
  (nDCG@10 ≈ 0.99, MRR/Recall = 1.000) — so per rule 9 no fine-tune can be *justified*
  here yet. The gate is real even when the corpus makes the result a tie.

### Incremental crawl (`server/src/noscia/ingest/`)
- **Conditional probe** (`crawl.py::check_conditional`) — a streamed `If-None-Match` /
  `If-Modified-Since` GET; a `304` skips the browser render entirely (proven live).
- **Content-hash diff** (`run.py`) — only changed/new chunks are re-embedded, vanished
  chunks pruned, unchanged chunks left untouched (a recrawl re-embedded **0** of 4).
  Chunk ids are position-stable (`sha256(url#ordinal)`) so the diff lands in place.
- **Adaptive cadence** — `corpus.sources_due()` maps each source's cadence (hourly …
  monthly) to a window; `ingest_due()` / `--due` recrawls only what's stale.
- `sources` gains `etag` / `last_modified` (idempotent `ALTER … IF NOT EXISTS`).

### Fine-tune pipeline (`server/src/noscia/train/`, `train` dep group)
- `synth.py` — BYOK LLM (OpenRouter via `get_secret`, never a raw key in source)
  writes ~3–5 synthetic queries per chunk → `data/train/synth_pairs.jsonl` (gitignored).
- `finetune.py` — **LoRA** fine-tune of Qwen3-0.6B (MNRL wrapped in MatryoshkaLoss at
  the deployed 256-dim prefix) + gradient checkpointing + capped batch/seq, so it trains
  in ~1 min on 18 GB unified memory with **no** MPS watermark override. Then re-runs the
  ESG eval base-vs-fine-tuned and prints the verdict — **ship only if it wins** (rule 9).
- This run: fine-tuned ties base (Δ nDCG = +0.000, saturated) → **DO NOT SHIP**, as
  expected. The adapter verifiably changes the model (cos(base, ft) = 0.988); the tie is
  real, not a no-op.

### Dropped / optional
- **Live-search fallback** (BYOK Exa/Tavily/Firecrawl) — **dropped by decision (rule 13):**
  no third-party search providers, no external data egress. Out-of-corpus queries return an
  honest low-confidence/empty state; the corpus is widened by adding seeds instead.
- ColBERT + MUVERA late-interaction path — optional; only if it beats single-vector on eval.

### Pinned versions
- httpx 0.28.1 (conditional probe + BYOK calls). `train` group (offline,
  `uv sync --group train`): datasets 5.0.0 · accelerate 1.13.0 · peft 0.19.1.

## Phase 1 — Core ESG search — 2026-06-14

The crawl → index → search pipeline is live end to end. An ESG question returns
relevant, highlighted, cited passages from the local index — verified through the
Vite proxy the browser uses. Built thin (8 curated seeds, 37 chunks) per the
"thin end-to-end first" rule.

### Ingestion (`server/src/noscia/ingest/`)
- `corpus/seeds.esg.yaml` — 8 curated ESG seeds (GHG Protocol, GRI, TCFD, IFRS S2,
  EU CSRD, MSCI, SBTi, CDP) grouped by `source_type` + recrawl cadence.
- `crawl.py` — crawl4ai 0.8.9 (headless Chromium) → clean markdown + title; per-URL
  error capture so one dead seed never sinks a run.
- `chunk.py` — tiktoken-accurate ~512-token windows (64 overlap) with a `content_hash`
  per chunk (for Phase 2 incremental crawl); strips markdown link/image/nav soup so
  passages read clean.
- `run.py` — the ingest runner + `python -m noscia.ingest.run` CLI; delete-by-url then
  upsert so a re-crawl never leaves stale chunks. Source status walks idle → crawling → done/error.

### Search (`server/src/noscia/search/`)
- `embed.py` — Qwen3-Embedding-0.6B via sentence-transformers; query-instruction vs raw-doc
  asymmetry; **Matryoshka** truncation 1024→256 + renormalize. Lazy-loaded, MPS/CUDA/CPU auto.
- `store.py` — `PgVectorStore` (the one `VectorStore` impl): `ON CONFLICT` upsert and the
  **hybrid RRF query in one Postgres round-trip** — dense CTE (pgvector `<=>`) + BM25 CTE
  (`pg_search` `@@@`), fused with Reciprocal Rank Fusion in SQL.
- `rerank.py` — `bge-reranker-v2-m3` cross-encoder over the fused top-50 (sigmoid-squashed scores).
- `highlight.py` — best-matching passage per result with `<mark>` spans; crawled HTML escaped
  before marking (no passage can inject markup).
- `pipeline.py` — the two tiers: **Quality** (embed → hybrid → rerank → highlight) and **Fast**
  (embed → dense-only ANN → highlight); returns the contract `SearchResponse` with the pipeline trace.

### Datastore
- `db/init/02-schema.sql` — `chunks` (`vector(256)` HNSW + `pg_search` bm25 index, content-addressed id)
  and `sources` (Corpus view state). Idempotent; applied at initdb and re-applied on startup via `db.init_schema()`.

### API + contract
- `/search` now runs the real pipeline. New `/corpus`, `/corpus/ingest`, `/corpus/add` endpoints.
- `contract.py` ⇄ `web/src/lib/api.ts` extended in lockstep: `CorpusStats`, `CorpusSource`,
  `CorpusResponse`, `AddSeedRequest`, `IngestRequest/Response`.
- App startup (lifespan) ensures schema + registers seeds idempotently.

### Frontend (`web/`)
- **Search view** fully wired: result list (`ResultRow` — #rank, source badge, `ScoreBar`,
  org·host, `<mark>` snippet, ● fresh) + split-pane `PassageReader` (source pill, meta strip,
  Highlighted↔Full-context toggle, Cite/Open actions). Empty/loading/error/done states.
- **Corpus view**: stat cards (chunks, pages, index size, model/dims) + sources table
  (status dot, counts, cadence, per-row recrawl) + add-&-crawl seed input.
- `SourceType` badge/dot maps the `source_type` string to the §8.2 color tokens (single source of truth).

### Pinned versions
- crawl4ai 0.8.9 · sentence-transformers 5.5.1 · torch 2.12.0 · transformers 5.10.2 ·
  numpy 2.4.6 · tiktoken 0.13.0 · pyyaml 6.0.3. Cooldown now **persisted** in
  `pyproject.toml` (`[tool.uv] exclude-newer`) so every `uv` resolve honors the 7-day window.

### Deferred to Phase 2 (noted, not silently skipped)
- Live streaming crawl progress (Phase 1 ingest is synchronous with status transitions).
- Full-page context in the reader's "Full-context" mode (currently drops `<mark>` spans only).
- Embedder/reranker eval harness (nDCG@10 / MRR on `corpus/eval/esg_queries.jsonl`).

## Phase 0 — Skeleton + guardrails — 2026-06-14

First buildable skeleton. The crawl → index → search pipeline and the UI surfaces
are stubbed but not implemented (Phase 1+). Everything below is verified green.

### Repo structure (locked to industry standard before building)
- Backend adopted **PyPA src-layout**: package `noscia` at `server/src/noscia/`, run via `uvicorn noscia.app:app`.
- Renamed the secrets module `secrets.py` → **`config.py`** (the old name shadows the Python stdlib `secrets`).
- Added a root **`package.json`** (a pnpm workspace requires one), `tests/`, `ruff`, `.python-version`, `.editorconfig`, CI workflow, and a proprietary `LICENSE` placeholder.
- Updated SPEC §3 repo layout + IMPLEMENTATION path references to match.

### Backend (`server/`)
- FastAPI app (`noscia.app`) with `GET /health` (pings Postgres via `SELECT 1`), plus contract-valid stubs `POST /search` and `GET /providers`.
- `contract.py` — the stable HTTP contract (Pydantic models), mirrored 1:1 in the frontend.
- `config.py` — `get_secret()` + `mask()`; the only seam that reads `.env` / env (never `os.environ` in app code).
- `db.py` — single SQLAlchemy engine + `ping()`.
- `user.py` — `CurrentUser` seam (`SoloUser` now; `HeaderUser` for SSO later).
- `search/store.py` — `VectorStore` interface (`PgVectorStore` impl lands in Phase 1).
- Tests: `pytest` (7 passing), `ruff` clean. Deps locked with the 7-day cooldown (`uv lock --exclude-newer 2026-06-07`).

### Frontend (`web/`)
- Vite + React 19 + TS scaffold; **Tailwind v4** with the §8.2 espresso design tokens defined in `@theme` (single source of truth — no hard-coded hex).
- Shell: 62px icon **Rail** + view router; four view shells — Search (functional empty split-pane wired to `/search`), Entity, Corpus (placeholders), **Settings · BYOK** (masked provider status from `/providers`).
- Live `/health` status pill; typed API client `src/lib/api.ts` mirroring the contract.
- `vitest` + Testing Library (1 smoke test passing); `eslint` clean; production build green.
- Dev server pinned to **port 5180** (`strictPort`) to avoid the crowded 5173 default.

### Datastore
- `docker-compose.yml` runs **ParadeDB `0.24.0-pg17`** (Postgres 17 + `pgvector` + `pg_search`) for the dev loop and the deployment (dev == prod).
- `db/init/01-extensions.sql` creates `vector` + `pg_search` on first init — both verified live.

### Guardrails (baked in from day one)
- pnpm workspace with `minimumReleaseAge: 10080` (7-day release cooldown); `renovate.json` carries the same across npm/PyPI/Cargo.
- `.gitignore` covers `.env`, `data/`, caches; `.env.example` ships `OPENROUTER_API_KEY` + `DATABASE_URL`.
- No AI attribution in git; commits authored under the GitHub no-reply identity.

### Verified end-to-end
- Through the Vite proxy the browser uses (`:5180` → `:8000`): `/api/health` → `{"status":"ok","db":true}`, `/api/providers` returns masked OpenRouter status.
- All 15 Phase 0 checklist items (IMPLEMENTATION §7) ticked.
