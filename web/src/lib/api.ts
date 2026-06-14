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
}

export interface SearchResponse {
  query: string
  tier: Tier
  results: SearchResult[]
  trace: PipelineTrace
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
}
