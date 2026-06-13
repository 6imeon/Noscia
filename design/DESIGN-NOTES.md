# Noscia — Frontend design exploration

Five interactive UI directions for Noscia's search surface, plus the research that shaped them. Open [`mockups/index.html`](mockups/index.html) to browse all five; each one links to the others via the top bar.

All mockups are **standalone HTML/CSS/vanilla-JS** — no build step, no CDN, no network calls (consistent with the local-first, supply-chain-cautious ethos in `SPEC.md` §11). Open them straight from disk, or:

```bash
cd design/mockups && python3 -m http.server 8080   # then visit localhost:8080
```

The sample ESG content (Scope 2 vs Scope 3 query; the entity table of FTSE companies) is **illustrative placeholder data for layout evaluation only — not real disclosures.** Company emissions figures, ratings and "controversies" are invented.

---

## What the research said

I looked at how today's neural-search and AI products present **cited, retrieved evidence**, and at HCI work on provenance/transparency. The signal that mattered:

1. **Show the passage, not the page.** Exa's whole differentiator is returning the *query-relevant passage* — and a *different* passage for the same URL depending on the query. This is exactly Noscia's "highlights" step (`SPEC.md` §5.5). Every design leads with the extracted passage, not a blue link. ([Exa vs Perplexity](https://exa.ai/versus/perplexity))

2. **There are four citation patterns; pick per context.** Inline highlights, direct quotations, multi-source references, and lightweight links. Point to the *exact* passage for factual claims; use hover-preview **and** click-through (dual-mode) to balance speed against thoroughness. ([ShapeOf.AI — Citations](https://www.shapeof.ai/patterns/citations))

3. **Make missing/weak evidence explicit.** Don't hide a broken or absent citation — surface it. This maps directly onto the spec's **evidence-or-null** rule for the entity agent (`SPEC.md` §11). The Workbench shows `cited / estimated / no-evidence` as three distinct dot states; the Cards show an explicit "citation not yet indexed" notice. ([ShapeOf.AI](https://www.shapeof.ai/patterns/citations))

4. **Provenance is worth visualising.** HCI work on research transparency and "visualization badges" argues that showing *where a result came from and how it was produced* increases trust and lets people judge quality. That's the whole premise of Direction 04. ([ACM Interactions — transparency in HCI](https://interactions.acm.org/blog/view/toward-a-consensus-on-research-transparency-for-hci))

5. **Entity results want a faceted panel + a table, with drill-down.** Faceted filters belong in a rail; results render as scannable tabular data; activated filters must be visibly indicated; each row drills down to detail. ([LogRocket — advanced search UX](https://blog.logrocket.com/ux-design/advanced-ux-search-principles/), [Fact-Finder — faceted search](https://www.fact-finder.com/blog/faceted-search/))

6. **ESG specifics.** Colour-code by category/source, place values beside benchmarks, keep emissions comparison legible (small multiples / consistent units), and make everything filterable and exportable. ([ESG needs data design](https://medium.com/clever-franke/esg-needs-data-design-part-2-0a1cda2107eb))

---

## The five directions

| # | Name | Layout | Best for | Signature move |
|---|------|--------|----------|----------------|
| 01 | **Research Console** | Two-pane, dark | Power users reading deeply | Click a result → right pane shows the highlight *in surrounding context*, with a highlight/full-context toggle |
| 02 | **Evidence Cards** | Single column, light/editorial | Trust-first reading, sharing | Passage as a pull-quote; hover a `[1]` chip → source-preview popover; explicit "missing citation" notice |
| 03 | **Entity Workbench** | Table + facet rail + drawer, dark | The §3 entity-search showpiece | Every cell carries an evidence dot (`cited/estimated/null`); click → drawer with the cited passage; CSV/JSON export |
| 04 | **Provenance Inspector** | Results + inspector, dark | Debugging relevance, demoing the pipeline | Per-result dense/BM25/rerank contribution bar; inspector explains *why* each result moved rank |
| 05 | **Command Palette** | Centered palette + peek | The Fast (<200 ms) tier; keyboard users | Raycast-style instant search; ↑/↓ to move, peek panel shows the passage; Fast↔Quality segmented control |

Each one exercises a different part of the spec's surface (search highlights, the Fast/Quality tiers from §5, the entity table from §3/§9, the hybrid pipeline from §5). They're deliberately distinct in **density, theme, and emphasis** rather than five reskins — the goal is to decide a *direction*, not pick a color.

### How they relate to the build

- The **search view** (Phase 1) is most directly served by **01**, **02**, or **05** — or a hybrid: a palette/instant entry (05) that expands into a console reader (01).
- The **entity-search view** (Phase 3 showpiece) is **03**, essentially as-is. This is the one with the least overlap with anything else, so it can be designed independently.
- **04** is less a day-one product surface than a **diagnostic/credibility layer** — valuable in the demo ("here's *why* it ranked") and during eval, and could live behind a "show provenance" toggle on any of the others.

A reasonable end state: **02 or 05 for plain search**, **03 for entity search**, with **04's score-breakdown** available as an expandable panel. 01 is the strongest single choice if you want one surface that does everything for a technical audience.

---

## Open questions for you

- **Theme:** dark (01/03/04/05) or light/editorial (02)? Affects the whole system.
- **Plain search default:** lean minimal/instant (05) or rich/two-pane (01)?
- **One surface or two?** Should plain search and entity search share a shell, or be distinct modes?
- Whether the **provenance layer (04)** is always-available, demo-only, or cut for v1.

---

## Sources

- [Exa vs Perplexity — neural search vs synthesized answers](https://exa.ai/versus/perplexity)
- [ShapeOf.AI — Citation UI patterns](https://www.shapeof.ai/patterns/citations)
- [ACM Interactions — research transparency in HCI](https://interactions.acm.org/blog/view/toward-a-consensus-on-research-transparency-for-hci)
- [LogRocket — advanced search UX best practices](https://blog.logrocket.com/ux-design/advanced-ux-search-principles/)
- [Fact-Finder — faceted search best practices](https://www.fact-finder.com/blog/faceted-search/)
- [Clever°Franke — ESG needs data design](https://medium.com/clever-franke/esg-needs-data-design-part-2-0a1cda2107eb)
- [Designing ESG dashboards for 2026](https://medium.com/@mokkup/designing-the-future-of-esg-dashboards-how-to-build-sustainability-reporting-tools-for-2026-6106d647c9ed)
