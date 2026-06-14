// Shared citation primitives for the grounded-output tabs (Answer + Structured):
// a numbered chip, an inline [n]→clickable-chip text renderer, and the Sources list
// that maps cited ranks to the result rows they came from. One place so both tabs
// render provenance identically.
import type { SearchResult } from '../lib/api'
import { SourceBadge } from './SourceType'

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

// A small numbered chip, shared by inline citations and the Sources list.
export function Chip({ n }: { n: number }) {
  return (
    <span className="inline-flex h-4 min-w-4 items-center justify-center rounded bg-accent/20 px-1 font-mono text-[9px] text-accent">
      {n}
    </span>
  )
}

// A row of clickable citation chips that open the cited result in the reader. Used by
// the Structured tab, where values carry their sources as a list rather than inline [n].
export function CiteChips({
  citations,
  results,
  onSelect,
}: {
  citations: number[]
  results: SearchResult[]
  onSelect: (r: SearchResult) => void
}) {
  if (citations.length === 0) return null
  return (
    <span className="ml-1.5 inline-flex gap-0.5 align-text-top">
      {citations.map((rank) => {
        const target = results.find((r) => r.rank === rank)
        return (
          <button
            key={rank}
            type="button"
            disabled={!target}
            onClick={() => target && onSelect(target)}
            title={target?.title}
            className="inline-flex h-4 min-w-4 items-center justify-center rounded bg-accent/20 px-1 font-mono text-[9px] text-accent transition-colors hover:bg-accent/40 disabled:opacity-50"
          >
            {rank}
          </button>
        )
      })}
    </span>
  )
}

// Exa-style source chips for a structured value: the cited rows shown by host (e.g.
// "esgtoday.com"), one chip per distinct host, "+N" when that host backs the value more
// than once. Clicking opens the first cited row for that host in the reader.
export function CiteHosts({
  citations,
  results,
  onSelect,
}: {
  citations: number[]
  results: SearchResult[]
  onSelect: (r: SearchResult) => void
}) {
  // distinct ranks → their result, grouped by host in citation order
  const seen = new Set<number>()
  const groups: { host: string; rows: SearchResult[] }[] = []
  for (const rank of citations) {
    if (seen.has(rank)) continue
    seen.add(rank)
    const row = results.find((r) => r.rank === rank)
    if (!row) continue
    const h = host(row.url)
    const g = groups.find((x) => x.host === h)
    if (g) g.rows.push(row)
    else groups.push({ host: h, rows: [row] })
  }
  if (groups.length === 0) return null
  return (
    <span className="ml-1.5 inline-flex flex-wrap gap-1 align-text-top">
      {groups.map((g) => (
        <button
          key={g.host}
          type="button"
          onClick={() => onSelect(g.rows[0])}
          title={g.rows.map((r) => r.title).join('\n')}
          className="inline-flex items-center gap-1 rounded bg-accent/15 px-1.5 font-mono text-[10px] text-accent transition-colors hover:bg-accent/30"
        >
          {g.host}
          {g.rows.length > 1 && <span className="text-dim">+{g.rows.length - 1}</span>}
        </button>
      ))}
    </span>
  )
}

// Split text on [n] markers so each citation renders as a clickable chip that opens
// the cited result in the reader.
export function CitedText({
  text,
  results,
  onSelect,
}: {
  text: string
  results: SearchResult[]
  onSelect: (r: SearchResult) => void
}) {
  return (
    <>
      {text.split(/(\[\d+\])/g).map((part, i) => {
        const m = part.match(/^\[(\d+)\]$/)
        if (!m) return <span key={i}>{part}</span>
        const rank = Number(m[1])
        const target = results.find((r) => r.rank === rank)
        return (
          <button
            key={i}
            type="button"
            disabled={!target}
            onClick={() => target && onSelect(target)}
            title={target?.title}
            className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-accent/20 px-1 align-text-top font-mono text-[9px] text-accent transition-colors hover:bg-accent/40 disabled:opacity-50"
          >
            {rank}
          </button>
        )
      })}
    </>
  )
}

// The cited results, listed under an answer/extraction — Perplexity-style provenance.
// `citations` are 1-based result ranks; deduped and shown in order.
export function Sources({
  citations,
  results,
  onSelect,
}: {
  citations: number[]
  results: SearchResult[]
  onSelect: (r: SearchResult) => void
}) {
  const seen = new Set<number>()
  const rows = citations
    .filter((rank) => !seen.has(rank) && seen.add(rank))
    .map((rank) => results.find((r) => r.rank === rank))
    .filter((r): r is SearchResult => Boolean(r))
  if (rows.length === 0) return null
  return (
    <div className="mt-5 border-t border-line/60 pt-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-wide text-dim">
        Sources · {rows.length}
      </div>
      <div className="space-y-1.5">
        {rows.map((r) => (
          <button
            key={r.rank}
            type="button"
            onClick={() => onSelect(r)}
            className="flex w-full items-start gap-2.5 rounded-md border border-line-2 bg-panel/40 px-2.5 py-2 text-left transition-colors hover:bg-hover"
          >
            <span className="mt-0.5">
              <Chip n={r.rank} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <SourceBadge type={r.source_type} />
                {r.published_at && (
                  <span className="font-mono text-[10px] text-dim">{r.published_at}</span>
                )}
              </div>
              <div className="mt-1 truncate text-xs text-ink">{r.title}</div>
              <div className="truncate font-mono text-[10px] text-dim">
                {r.org ? `${r.org} · ` : ''}
                {host(r.url)}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
