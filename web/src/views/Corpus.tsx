// Corpus & index view (Phase 1, SPEC §8.4): stat cards + sources table (status,
// counts, cadence, per-row recrawl) + an add-&-crawl seed input. Wired to /corpus,
// /corpus/ingest, /corpus/add. Ingest is synchronous for the demo — the row shows
// 'crawling' while the request is in flight; live progress streaming is Phase 2.
import { useCallback, useEffect, useState } from 'react'
import {
  api,
  type CorpusResponse,
  type CorpusSource,
  type SourceStatus,
  type SourceType,
} from '../lib/api'
import { SourceDot } from '../components/SourceType'

const SOURCE_TYPES: SourceType[] = ['framework', 'regulator', 'ratings', 'report', 'ngo', 'news']

type Load =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; data: CorpusResponse }

function bytes(n: number): string {
  if (n < 1024) return `${n} B`
  const u = ['KB', 'MB', 'GB']
  let v = n / 1024
  let i = 0
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(1)} ${u[i]}`
}

export function Corpus() {
  const [load, setLoad] = useState<Load>({ kind: 'loading' })
  const [busy, setBusy] = useState<Set<string>>(new Set())

  const refresh = useCallback(async () => {
    try {
      const data = await api.corpus()
      setLoad({ kind: 'ready', data })
    } catch (e) {
      setLoad({ kind: 'error', message: e instanceof Error ? e.message : 'failed to load corpus' })
    }
  }, [])

  useEffect(() => {
    let alive = true
    const init = async () => {
      try {
        const data = await api.corpus()
        if (alive) setLoad({ kind: 'ready', data })
      } catch (e) {
        if (alive)
          setLoad({ kind: 'error', message: e instanceof Error ? e.message : 'failed to load corpus' })
      }
    }
    void init()
    return () => {
      alive = false
    }
  }, [])

  const recrawl = async (url: string) => {
    setBusy((b) => new Set(b).add(url))
    try {
      await api.ingest({ urls: [url] })
      await refresh()
    } finally {
      setBusy((b) => {
        const n = new Set(b)
        n.delete(url)
        return n
      })
    }
  }

  if (load.kind === 'loading') return <div className="p-6 text-sm text-dim">Loading corpus…</div>
  if (load.kind === 'error')
    return <div className="p-6 text-sm text-accent-2">Failed to load — {load.message}</div>

  const { stats, sources } = load.data
  return (
    <div className="h-full overflow-auto p-6">
      <h1 className="mb-4 text-lg text-ink">Corpus &amp; index</h1>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="chunks indexed" value={stats.chunks.toLocaleString()} />
        <Stat label="source pages" value={stats.pages.toLocaleString()} />
        <Stat label="index size" value={bytes(stats.index_bytes)} />
        <Stat label="embedding" value={`${stats.embed_dims}-dim`} sub={stats.embed_model} />
      </div>

      <AddSeed busy={busy.size > 0} onAdded={refresh} />

      <div className="overflow-hidden rounded-md border border-line">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line bg-panel-2 font-mono text-[10px] uppercase tracking-wide text-dim">
              <Th>source</Th>
              <Th>type</Th>
              <Th className="text-right">pages</Th>
              <Th className="text-right">chunks</Th>
              <Th>last crawl</Th>
              <Th>cadence</Th>
              <Th>status</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {sources.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-dim">
                  No sources yet — add a seed above.
                </td>
              </tr>
            ) : (
              sources.map((s) => (
                <SourceRow
                  key={s.url}
                  source={s}
                  busy={busy.has(s.url)}
                  onRecrawl={() => recrawl(s.url)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-md border border-line bg-panel px-4 py-3">
      <div className="font-mono text-[10px] uppercase tracking-wide text-dim">{label}</div>
      <div className="mt-1 text-xl text-ink">{value}</div>
      {sub && <div className="mt-0.5 truncate font-mono text-[10px] text-dim">{sub}</div>}
    </div>
  )
}

function Th({ children, className = '' }: { children?: React.ReactNode; className?: string }) {
  return <th className={`px-3 py-2 text-left font-normal ${className}`}>{children}</th>
}

function SourceRow({
  source,
  busy,
  onRecrawl,
}: {
  source: CorpusSource
  busy: boolean
  onRecrawl: () => void
}) {
  const crawling = busy || source.status === 'crawling'
  let host = source.url
  try {
    host = new URL(source.url).hostname.replace(/^www\./, '')
  } catch {
    /* keep raw */
  }
  return (
    <tr className="border-b border-line-2 last:border-0 hover:bg-hover">
      <td className="max-w-[220px] px-3 py-2">
        <div className="truncate text-ink">{source.org ?? host}</div>
        <div className="truncate font-mono text-[10px] text-dim">{host}</div>
      </td>
      <td className="px-3 py-2">
        <span className="flex items-center gap-1.5 font-mono text-[11px] text-muted">
          <SourceDot type={source.source_type} />
          {source.source_type}
        </span>
      </td>
      <td className="px-3 py-2 text-right font-mono text-muted">{source.pages}</td>
      <td className="px-3 py-2 text-right font-mono text-muted">{source.chunks}</td>
      <td className="px-3 py-2 font-mono text-[11px] text-dim">
        {source.last_crawl ? new Date(source.last_crawl).toLocaleDateString() : '—'}
      </td>
      <td className="px-3 py-2 font-mono text-[11px] text-dim">{source.cadence}</td>
      <td className="px-3 py-2">
        <StatusBadge status={crawling ? 'crawling' : source.status} error={source.error} />
      </td>
      <td className="px-3 py-2 text-right">
        <button
          type="button"
          onClick={onRecrawl}
          disabled={crawling}
          className="rounded border border-line px-2 py-1 font-mono text-[10px] text-muted hover:bg-hover disabled:opacity-40"
        >
          {crawling ? '…' : 'recrawl'}
        </button>
      </td>
    </tr>
  )
}

function StatusBadge({ status, error }: { status: SourceStatus; error: string | null }) {
  const map: Record<SourceStatus, { color: string; label: string }> = {
    idle: { color: 'var(--color-dim)', label: 'idle' },
    crawling: { color: 'var(--color-warn)', label: 'crawling' },
    done: { color: 'var(--color-ok)', label: 'done' },
    error: { color: 'var(--color-accent-2)', label: 'error' },
  }
  const { color, label } = map[status]
  return (
    <span
      className="flex items-center gap-1.5 font-mono text-[11px]"
      style={{ color }}
      title={error ?? undefined}
    >
      <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} />
      {status === 'crawling' ? <span className="animate-pulse">{label}</span> : label}
    </span>
  )
}

function AddSeed({ busy, onAdded }: { busy: boolean; onAdded: () => Promise<void> }) {
  const [url, setUrl] = useState('')
  const [type, setType] = useState<SourceType>('framework')
  const [pending, setPending] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return
    setPending(true)
    setErr(null)
    try {
      const res = await api.addSeed({ url: url.trim(), source_type: type })
      if (!res.ok && res.errors.length) setErr(res.errors[0])
      else setUrl('')
      await onAdded()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'add failed')
    } finally {
      setPending(false)
    }
  }

  return (
    <form onSubmit={submit} className="mb-4 flex flex-wrap items-center gap-2">
      <input
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://… seed URL to crawl"
        className="min-w-[260px] flex-1 rounded-md border border-line bg-field px-3 py-2 text-sm text-ink placeholder:text-dim focus:border-accent focus:outline-none"
      />
      <select
        value={type}
        onChange={(e) => setType(e.target.value as SourceType)}
        className="rounded-md border border-line bg-field px-2 py-2 font-mono text-xs text-muted focus:border-accent focus:outline-none"
      >
        {SOURCE_TYPES.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
      <button
        type="submit"
        disabled={pending || busy}
        className="rounded-md border border-accent px-3 py-2 font-mono text-xs text-accent hover:bg-hover disabled:opacity-40"
      >
        {pending ? 'crawling…' : '＋ Add & crawl'}
      </button>
      {err && <span className="w-full font-mono text-[11px] text-accent-2">{err}</span>}
    </form>
  )
}
