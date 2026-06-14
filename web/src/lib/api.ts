// Typed client for the backend HTTP contract.
// MIRRORS server/src/noscia/contract.py EXACTLY — change both together, never one
// alone (SPEC §2 rule 3 / §11). The dev server proxies /api/* → FastAPI (vite.config.ts).

const BASE = '/api'

export type Tier = 'fast' | 'quality'

// Single source of truth for source-type strings → §8.2 color tokens (frontend maps).
export type SourceType = 'framework' | 'regulator' | 'ratings' | 'report' | 'ngo' | 'news'

export interface HealthResponse {
  status: 'ok' | 'degraded'
  db: boolean
  version: string
}

export interface SearchRequest {
  query: string
  tier: Tier
  top_k?: number
  // Opt-in, BYOK: synthesize one query-focused answer over the top passages.
  // Ignored (answer stays null) when no reasoning key is configured.
  summarize?: boolean
}

export interface PipelineTrace {
  dense: number
  bm25: number
  fused: number
  reranked: number
}

export interface SearchResult {
  rank: number
  url: string
  title: string
  org: string | null
  source_type: SourceType
  score: number
  highlight: string
  fresh: boolean
  published_at?: string | null // document publish date (ISO YYYY-MM-DD), null if unknown
}

export interface SearchResponse {
  query: string
  tier: Tier
  results: SearchResult[]
  trace: PipelineTrace
  summarized?: boolean
  answer?: string | null
  answer_citations?: number[]
}

// --- /structured (BYOK schema extraction over the top passages) ---
export interface StructuredField {
  name: string
  description?: string
}

export interface StructuredRequest {
  query: string
  tier: Tier
  fields: StructuredField[] // empty ⇒ AUTO mode (fields inferred from the query)
}

export interface ExtractedField {
  name: string
  value: string | null // may contain inline [n] citations; null when unsupported
  citations: number[]
}

export interface StructuredResponse {
  query: string
  tier: Tier
  results: SearchResult[]
  fields: ExtractedField[] // the answer as a flat object — snake_case keys (AUTO) or pinned (MANUAL)
  extracted: boolean
  auto: boolean // fields were inferred from the query (AUTO) vs a pinned schema (MANUAL)
}

export interface ProviderKeyStatus {
  provider: string
  configured: boolean
  masked: string
}

export interface ProvidersResponse {
  providers: ProviderKeyStatus[]
  default_provider: string
  default_tier: Tier
}

// --- /corpus (index stats + sources; Corpus view §8.4) ---
export interface CorpusStats {
  chunks: number
  sources: number
  pages: number
  index_bytes: number
  embed_model: string
  embed_dims: number
}

export type SourceStatus = 'idle' | 'crawling' | 'done' | 'error'

export interface CorpusSource {
  url: string
  source_type: SourceType
  org: string | null
  cadence: string
  status: SourceStatus
  pages: number
  chunks: number
  last_crawl: string | null
  error: string | null
}

export interface CorpusResponse {
  stats: CorpusStats
  sources: CorpusSource[]
}

export interface AddSeedRequest {
  url: string
  source_type: SourceType
  org?: string | null
  cadence?: string
}

export interface IngestRequest {
  urls?: string[] | null
}

export interface IngestResponse {
  ok: boolean
  indexed_pages: number
  chunks: number
  errors: string[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${init?.method ?? 'GET'} ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<HealthResponse>('/health'),
  providers: () => request<ProvidersResponse>('/providers'),
  search: (body: SearchRequest) =>
    request<SearchResponse>('/search', { method: 'POST', body: JSON.stringify(body) }),
  structured: (body: StructuredRequest) =>
    request<StructuredResponse>('/structured', { method: 'POST', body: JSON.stringify(body) }),
  corpus: () => request<CorpusResponse>('/corpus'),
  ingest: (body: IngestRequest = {}) =>
    request<IngestResponse>('/corpus/ingest', { method: 'POST', body: JSON.stringify(body) }),
  addSeed: (body: AddSeedRequest) =>
    request<IngestResponse>('/corpus/add', { method: 'POST', body: JSON.stringify(body) }),
}
