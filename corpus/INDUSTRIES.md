# Industry catalog — 10 verticals + curated authoritative sources

Companion to [../MULTI_INDUSTRY.md](../MULTI_INDUSTRY.md). These are the **seed lists** for
the multi-industry feature: one vertical per section, each a narrow set of *authoritative*
sites (rule 11 — quality over coverage; rule 13 — our own curated index, never open-web
discovery). Every block uses the existing seed schema (see
[seeds.esg.yaml](seeds.esg.yaml) header) so each drops straight into `corpus/seeds/<id>.yaml`.

> **Before first crawl:** these URLs are authoritative *landing/section* pages chosen for
> stable domains, but agencies restructure paths — do a quick reachability pass (the
> `/corpus/add` flow surfaces a failed crawl) and tune `crawl.max_depth`/`max_pages` per
> seed to stay in the ~300–500 page/vertical target. `source_type` reuses the ESG literals
> (`framework | regulator | ratings | report | ngo | news`) loosely for non-ESG verticals
> (v1 decision, §8 of the design doc) — widen the literal set later if a vertical needs it.

## The catalog (`corpus/industries.yaml`)

```yaml
industries:
  - { id: esg,           label: "ESG & Sustainability",        icon: leaf,     seeds: seeds/esg.yaml,
      blurb: "Standards, regulators, ratings, and target-setters for corporate sustainability." }
  - { id: economics,     label: "Economics & Macro",           icon: chart,    seeds: seeds/economics.yaml,
      blurb: "Central banks, statistical agencies, and macroeconomic research." }
  - { id: healthcare,    label: "Healthcare & Public Health",  icon: heart,    seeds: seeds/healthcare.yaml,
      blurb: "Health agencies, clinical guidelines, and evidence reviews." }
  - { id: cybersecurity, label: "Cybersecurity",               icon: shield,   seeds: seeds/cybersecurity.yaml,
      blurb: "Security frameworks, advisories, and threat-intelligence standards." }
  - { id: ai,            label: "Artificial Intelligence",     icon: cpu,      seeds: seeds/ai.yaml,
      blurb: "AI research repositories, governance frameworks, and policy bodies." }
  - { id: energy,        label: "Energy & Climate",            icon: bolt,     seeds: seeds/energy.yaml,
      blurb: "Energy agencies, climate science, and the transition evidence base." }
  - { id: finance,       label: "Financial Regulation",        icon: bank,     seeds: seeds/finance.yaml,
      blurb: "Banking supervisors, market regulators, and global standard-setters." }
  - { id: agriculture,   label: "Agriculture & Food",          icon: wheat,    seeds: seeds/agriculture.yaml,
      blurb: "Food & agriculture agencies, safety standards, and research institutes." }
  - { id: pharma,        label: "Pharma & Drug Regulation",    icon: pill,     seeds: seeds/pharma.yaml,
      blurb: "Drug regulators, harmonisation standards, and trial registries." }
  - { id: space,         label: "Space & Aerospace",           icon: rocket,   seeds: seeds/space.yaml,
      blurb: "Space agencies, aviation/space regulators, and technical archives." }
```

---

## 1. ESG & Sustainability — `seeds/esg.yaml`

Already built — the existing [seeds.esg.yaml](seeds.esg.yaml) (21 seeds: GHG Protocol, GRI,
TCFD, TNFD, SASB/IFRS, ISSB, EC CSRD, EFRAG, US SEC, MSCI, Sustainalytics, S&P Global, SBTi,
CDP, UN PRI, UN Global Compact, Ceres, WRI, WBCSD, ESG Today). Moves here unchanged with
`industry: esg`.

## 2. Economics & Macro — `seeds/economics.yaml`

```yaml
seeds:
  - { url: https://www.federalreserve.gov/publications.htm, source_type: regulator, org: "US Federal Reserve", cadence: weekly }
  - { url: https://www.ecb.europa.eu/press/research-publications/html/index.en.html, source_type: regulator, org: "European Central Bank", cadence: weekly }
  - { url: https://www.bis.org/forum/research.htm, source_type: regulator, org: "Bank for International Settlements", cadence: weekly }
  - { url: https://www.imf.org/en/Publications, source_type: report, org: "IMF", cadence: weekly, crawl: { max_depth: 1, max_pages: 30, max_pdfs: 6 } }
  - { url: https://www.worldbank.org/en/research, source_type: report, org: "World Bank", cadence: weekly }
  - { url: https://www.oecd.org/en/topics/economy.html, source_type: ngo, org: "OECD", cadence: weekly }
  - { url: https://www.nber.org/papers, source_type: report, org: "NBER", cadence: weekly, crawl: { max_depth: 1, max_pages: 30 } }
  - { url: https://www.bea.gov/news/current-releases, source_type: regulator, org: "US Bureau of Economic Analysis", cadence: daily }
  - { url: https://www.bls.gov/bls/newsrels.htm, source_type: regulator, org: "US Bureau of Labor Statistics", cadence: daily }
  - { url: https://www.bankofengland.co.uk/news/publications, source_type: regulator, org: "Bank of England", cadence: weekly }
```

## 3. Healthcare & Public Health — `seeds/healthcare.yaml`

```yaml
seeds:
  - { url: https://www.who.int/publications, source_type: ngo, org: "World Health Organization", cadence: weekly, crawl: { max_depth: 1, max_pages: 30, max_pdfs: 6 } }
  - { url: https://www.cdc.gov/library/researchguides/, source_type: regulator, org: "US CDC", cadence: weekly }
  - { url: https://www.nih.gov/health-information, source_type: regulator, org: "US NIH", cadence: weekly }
  - { url: https://www.ecdc.europa.eu/en/publications-data, source_type: regulator, org: "ECDC", cadence: weekly }
  - { url: https://www.nice.org.uk/guidance, source_type: framework, org: "NICE (UK)", cadence: monthly, crawl: { max_depth: 1, max_pages: 30 } }
  - { url: https://www.uspreventiveservicestaskforce.org/uspstf/topic_search_results, source_type: framework, org: "USPSTF", cadence: monthly }
  - { url: https://www.cochranelibrary.com/cdsr/reviews, source_type: report, org: "Cochrane", cadence: weekly }
  - { url: https://www.ahrq.gov/research/findings/index.html, source_type: regulator, org: "US AHRQ", cadence: monthly }
```

## 4. Cybersecurity — `seeds/cybersecurity.yaml`

```yaml
seeds:
  - { url: https://csrc.nist.gov/publications, source_type: framework, org: "NIST CSRC", cadence: weekly, crawl: { max_depth: 1, max_pages: 30, max_pdfs: 8 } }
  - { url: https://www.cisa.gov/news-events/cybersecurity-advisories, source_type: regulator, org: "US CISA", cadence: daily }
  - { url: https://attack.mitre.org/, source_type: framework, org: "MITRE ATT&CK", cadence: monthly, crawl: { max_depth: 2, max_pages: 40 } }
  - { url: https://owasp.org/www-project-top-ten/, source_type: ngo, org: "OWASP", cadence: monthly }
  - { url: https://www.cisecurity.org/controls, source_type: framework, org: "Center for Internet Security", cadence: monthly }
  - { url: https://www.enisa.europa.eu/publications, source_type: regulator, org: "ENISA", cadence: weekly }
  - { url: https://www.cve.org/, source_type: framework, org: "CVE / MITRE", cadence: daily }
  - { url: https://krebsonsecurity.com/, source_type: news, org: "Krebs on Security", cadence: daily }
```

## 5. Artificial Intelligence — `seeds/ai.yaml`

```yaml
seeds:
  - { url: https://arxiv.org/list/cs.AI/recent, source_type: report, org: "arXiv cs.AI", cadence: daily, crawl: { max_depth: 1, max_pages: 40 } }
  - { url: https://arxiv.org/list/cs.LG/recent, source_type: report, org: "arXiv cs.LG", cadence: daily, crawl: { max_depth: 1, max_pages: 40 } }
  - { url: https://www.nist.gov/itl/ai-risk-management-framework, source_type: framework, org: "NIST AI RMF", cadence: monthly }
  - { url: https://oecd.ai/en/, source_type: ngo, org: "OECD.AI Policy Observatory", cadence: weekly }
  - { url: https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai, source_type: regulator, org: "European Commission (AI Act)", cadence: weekly }
  - { url: https://hai.stanford.edu/research, source_type: ngo, org: "Stanford HAI", cadence: weekly }
  - { url: https://aclanthology.org/, source_type: report, org: "ACL Anthology", cadence: weekly, crawl: { max_depth: 1, max_pages: 30 } }
  - { url: https://www.anthropic.com/research, source_type: report, org: "Anthropic", cadence: weekly }
```

## 6. Energy & Climate — `seeds/energy.yaml`

```yaml
seeds:
  - { url: https://www.iea.org/analysis, source_type: report, org: "International Energy Agency", cadence: weekly, crawl: { max_depth: 1, max_pages: 30, max_pdfs: 6 } }
  - { url: https://www.irena.org/Publications, source_type: ngo, org: "IRENA", cadence: weekly }
  - { url: https://www.eia.gov/analysis/, source_type: regulator, org: "US Energy Information Administration", cadence: daily }
  - { url: https://www.ipcc.ch/reports/, source_type: framework, org: "IPCC", cadence: monthly, crawl: { max_depth: 1, max_pages: 25, max_pdfs: 8 } }
  - { url: https://www.nrel.gov/research/publications.html, source_type: report, org: "NREL", cadence: weekly }
  - { url: https://ember-energy.org/insights/, source_type: ngo, org: "Ember", cadence: weekly }
  - { url: https://www.energy.gov/science-innovation/energy-sources, source_type: regulator, org: "US Department of Energy", cadence: weekly }
  - { url: https://ieefa.org/research, source_type: ngo, org: "IEEFA", cadence: weekly }
```

## 7. Financial Regulation — `seeds/finance.yaml`

```yaml
seeds:
  - { url: https://www.bis.org/bcbs/publications.htm, source_type: framework, org: "Basel Committee (BIS)", cadence: weekly, crawl: { max_depth: 1, max_pages: 30, max_pdfs: 6 } }
  - { url: https://www.sec.gov/rules-regulations, source_type: regulator, org: "US SEC", cadence: daily }
  - { url: https://www.fdic.gov/news/, source_type: regulator, org: "US FDIC", cadence: weekly }
  - { url: https://www.fca.org.uk/publications, source_type: regulator, org: "UK FCA", cadence: weekly }
  - { url: https://www.esma.europa.eu/publications-and-data, source_type: regulator, org: "ESMA", cadence: weekly }
  - { url: https://www.iosco.org/publications/, source_type: framework, org: "IOSCO", cadence: monthly }
  - { url: https://www.fsb.org/publications/, source_type: framework, org: "Financial Stability Board", cadence: weekly }
  - { url: https://www.cftc.gov/PressRoom/PressReleases, source_type: regulator, org: "US CFTC", cadence: weekly }
```

## 8. Agriculture & Food — `seeds/agriculture.yaml`

```yaml
seeds:
  - { url: https://www.fao.org/publications/en, source_type: ngo, org: "FAO", cadence: weekly, crawl: { max_depth: 1, max_pages: 30, max_pdfs: 6 } }
  - { url: https://www.ers.usda.gov/publications/, source_type: report, org: "USDA Economic Research Service", cadence: weekly }
  - { url: https://www.efsa.europa.eu/en/publications, source_type: regulator, org: "EFSA", cadence: weekly }
  - { url: https://www.fao.org/fao-who-codexalimentarius/standards/en/, source_type: framework, org: "Codex Alimentarius", cadence: monthly }
  - { url: https://www.cgiar.org/research/publications/, source_type: ngo, org: "CGIAR", cadence: weekly }
  - { url: https://www.ifpri.org/publications/, source_type: report, org: "IFPRI", cadence: weekly }
  - { url: https://www.ifoam.bio/our-work/how/standards-certification, source_type: ngo, org: "IFOAM Organics International", cadence: monthly }
  - { url: https://www.oecd.org/en/topics/agriculture.html, source_type: ngo, org: "OECD Agriculture", cadence: weekly }
```

## 9. Pharma & Drug Regulation — `seeds/pharma.yaml`

```yaml
seeds:
  - { url: https://www.fda.gov/drugs/development-approval-process-drugs, source_type: regulator, org: "US FDA", cadence: weekly, crawl: { max_depth: 1, max_pages: 30 } }
  - { url: https://www.ema.europa.eu/en/news-events/whats-new, source_type: regulator, org: "European Medicines Agency", cadence: weekly }
  - { url: https://www.ich.org/page/ich-guidelines, source_type: framework, org: "ICH", cadence: monthly, crawl: { max_depth: 1, max_pages: 25, max_pdfs: 8 } }
  - { url: https://www.who.int/teams/health-product-policy-and-standards/standards-and-specifications, source_type: framework, org: "WHO Health Product Standards", cadence: monthly }
  - { url: https://www.gov.uk/government/organisations/medicines-and-healthcare-products-regulatory-agency, source_type: regulator, org: "UK MHRA", cadence: weekly }
  - { url: https://clinicaltrials.gov/, source_type: report, org: "ClinicalTrials.gov", cadence: weekly, crawl: { max_depth: 1, max_pages: 20 } }
  - { url: https://www.usp.org/health-quality-safety, source_type: framework, org: "US Pharmacopeia", cadence: monthly }
  - { url: https://www.pmda.go.jp/english/, source_type: regulator, org: "Japan PMDA", cadence: monthly }
```

## 10. Space & Aerospace — `seeds/space.yaml`

```yaml
seeds:
  - { url: https://www.nasa.gov/news/all-news/, source_type: regulator, org: "NASA", cadence: daily }
  - { url: https://ntrs.nasa.gov/, source_type: report, org: "NASA Technical Reports Server", cadence: weekly, crawl: { max_depth: 1, max_pages: 30, max_pdfs: 8 } }
  - { url: https://www.esa.int/About_Us/ESA_Publications, source_type: regulator, org: "European Space Agency", cadence: weekly }
  - { url: https://www.faa.gov/space, source_type: regulator, org: "US FAA (Commercial Space)", cadence: weekly }
  - { url: https://www.unoosa.org/oosa/en/ourwork/index.html, source_type: ngo, org: "UNOOSA", cadence: monthly }
  - { url: https://www.itu.int/en/ITU-R/space/Pages/default.aspx, source_type: regulator, org: "ITU (Radiocommunication)", cadence: monthly }
  - { url: https://www.aiaa.org/publications, source_type: ngo, org: "AIAA", cadence: monthly }
  - { url: https://spacenews.com/, source_type: news, org: "SpaceNews", cadence: daily }
```

---

## Notes on curation

- **~8 seeds/vertical** keeps each corpus narrow (rule 11); depth comes from each
  authoritative site's *own* internal links + curated PDFs, never open-web crawl (rule 13).
- **Cadence** is tuned per source character — agency newsrooms `daily`, research/publication
  hubs `weekly`, slow-moving standards `monthly` — so `--due` recrawls only what churns.
- **PDF caps** (`max_pdfs`) are raised on document-heavy bodies (IMF, IPCC, ICH, NIST, NASA
  NTRS) where the substance lives in reports, mirroring the ESG corpus's PDF strategy.
- **Per-vertical eval** (`corpus/eval/<id>_queries.jsonl`) is the honest gate before calling
  any of these production-ready — ranking quality is decided on the vertical's own corpus,
  not assumed (rule 9; Phase D of the checklist).
