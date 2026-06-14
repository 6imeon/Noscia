// Search view (Phase 1 primary, SPEC §8.4): shared search bar + Quality/Fast
// toggle → result list (badge/score/snippet) + passage reader. Selecting a row
// opens its cited passage in the reader. Empty/loading/error/done states.
import { useEffect, useState } from 'react'
import { api, type SearchResponse, type SearchResult, type Tier } from '../lib/api'
import { AnswerBanner } from '../components/AnswerBanner'
import { PassageReader } from '../components/PassageReader'
import { ResultRow } from '../components/ResultRow'
import { SearchBar } from '../components/SearchBar'

type Status =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'done'; data: SearchResponse }

export function Search() {
  const [query, setQuery] = useState('')
  const [tier, setTier] = useState<Tier>('quality')
  const [summarize, setSummarize] = useState(true) // on by default; only sent when a key exists
  const [keyConfigured, setKeyConfigured] = useState(false)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [selected, setSelected] = useState<SearchResult | null>(null)

  // BYOK summaries need a reasoning key — gate the toggle on /providers status.
  useEffect(() => {
    api
      .providers()
      .then((p) => setKeyConfigured(p.providers.some((k) => k.configured)))
      .catch(() => setKeyConfigured(false))
  }, [])

  const run = async () => {
    if (!query.trim()) return
    setStatus({ kind: 'loading' })
    setSelected(null)
    try {
      const data = await api.search({ query, tier, summarize: summarize && keyConfigured })
      setStatus({ kind: 'done', data })
      setSelected(data.results[0] ?? null)
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
          summarize={summarize}
          onSummarize={setSummarize}
          summarizeAvailable={keyConfigured}
          busy={status.kind === 'loading'}
        />
      </div>

      {status.kind === 'done' && <AnswerBanner data={status.data} onSelect={setSelected} />}

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <section className="min-h-0 overflow-auto border-r border-line">
          <ResultList status={status} selected={selected} onSelect={setSelected} />
        </section>
        <section className="min-h-0 overflow-auto">
          <PassageReader result={selected} />
        </section>
      </div>
    </div>
  )
}

function ResultList({
  status,
  selected,
  onSelect,
}: {
  status: Status
  selected: SearchResult | null
  onSelect: (r: SearchResult) => void
}) {
  if (status.kind === 'idle')
    return <Placeholder>Ask an ESG question to search the corpus.</Placeholder>
  if (status.kind === 'loading')
    return (
      <div className="space-y-2 p-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-20 animate-pulse rounded-md bg-panel-2" />
        ))}
      </div>
    )
  if (status.kind === 'error')
    return <Placeholder tone="error">Search failed — {status.message}</Placeholder>

  const { results, tier, trace } = status.data
  return (
    <div>
      <header className="sticky top-0 flex items-center justify-between border-b border-line bg-bg px-4 py-2 font-mono text-[11px] text-muted">
        <span>
          {results.length} passages · {tier} tier
        </span>
        <span className={tier === 'fast' ? 'opacity-35' : ''}>
          dense {trace.dense} + bm25 {trace.bm25} → rrf → rerank {trace.reranked}
        </span>
      </header>
      {results.length === 0 ? (
        <Placeholder>No matching passages. Try different terms, or widen the corpus in Corpus.</Placeholder>
      ) : (
        results.map((r) => (
          <ResultRow
            key={`${r.rank}-${r.url}`}
            result={r}
            active={selected?.rank === r.rank && selected?.url === r.url}
            onSelect={() => onSelect(r)}
          />
        ))
      )}
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
    <div className={`p-6 text-sm ${tone === 'error' ? 'text-accent-2' : 'text-dim'}`}>
      {children}
    </div>
  )
}
