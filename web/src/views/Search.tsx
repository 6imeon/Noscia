// Search view (Phase 1 primary) — Phase 0 ships the shell: shared search bar +
// tier toggle wired to /search (returns empty for now), split pane with
// empty/loading/error states (SPEC §8.4).
import { useState } from 'react'
import { api, type SearchResponse, type Tier } from '../lib/api'
import { SearchBar } from '../components/SearchBar'

type Status =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'done'; data: SearchResponse }

export function Search() {
  const [query, setQuery] = useState('')
  const [tier, setTier] = useState<Tier>('quality')
  const [status, setStatus] = useState<Status>({ kind: 'idle' })

  const run = async () => {
    if (!query.trim()) return
    setStatus({ kind: 'loading' })
    try {
      const data = await api.search({ query, tier })
      setStatus({ kind: 'done', data })
    } catch (e) {
      setStatus({ kind: 'error', message: e instanceof Error ? e.message : 'search failed' })
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-5 py-3">
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={run}
          tier={tier}
          onTier={setTier}
          busy={status.kind === 'loading'}
        />
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        {/* result list */}
        <section className="min-h-0 overflow-auto border-r border-line">
          <ResultList status={status} />
        </section>
        {/* reader */}
        <section className="min-h-0 overflow-auto p-6 text-sm text-dim">
          select a result →
        </section>
      </div>
    </div>
  )
}

function ResultList({ status }: { status: Status }) {
  if (status.kind === 'idle')
    return <Placeholder>Ask an ESG question to search the corpus.</Placeholder>
  if (status.kind === 'loading')
    return (
      <div className="space-y-2 p-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-16 animate-pulse rounded-md bg-panel-2" />
        ))}
      </div>
    )
  if (status.kind === 'error')
    return <Placeholder tone="error">Search failed — {status.message}</Placeholder>

  const { results, tier, trace } = status.data
  return (
    <div>
      <header className="flex items-center justify-between border-b border-line px-4 py-2 font-mono text-[11px] text-muted">
        <span>
          {results.length} passages · {tier} tier
        </span>
        <span className={tier === 'fast' ? 'opacity-35' : ''}>
          dense {trace.dense} + bm25 {trace.bm25} → rrf → rerank {trace.reranked}
        </span>
      </header>
      {results.length === 0 ? (
        <Placeholder>
          No results yet — the index is empty until Phase 1 ingestion runs.
        </Placeholder>
      ) : null}
    </div>
  )
}

function Placeholder({
  children,
  tone = 'muted',
}: {
  children: React.ReactNode
  tone?: 'muted' | 'error'
}) {
  return (
    <div
      className={`p-6 text-sm ${tone === 'error' ? 'text-accent-2' : 'text-dim'}`}
    >
      {children}
    </div>
  )
}
