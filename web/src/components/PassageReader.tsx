// Reader pane (§8.4): source pill, title, url, meta strip, a Highlighted ↔
// Full-context toggle, the cited passage, and actions. Phase 1 returns the marked
// passage only (no surrounding page text yet), so "Full-context" simply drops the
// <mark> spans; carrying full-page context is a Phase 2 refinement.
import { useState } from 'react'
import type { SearchResult } from '../lib/api'
import { SourceBadge } from './SourceType'

type Scope = 'highlighted' | 'full'

function stripMarks(html: string): string {
  return html.replace(/<\/?mark>/g, '')
}

export function PassageReader({ result }: { result: SearchResult | null }) {
  const [scope, setScope] = useState<Scope>('highlighted')
  const [copied, setCopied] = useState(false)

  if (!result)
    return <div className="p-6 text-sm text-dim">select a result →</div>

  const body = scope === 'highlighted' ? result.highlight : stripMarks(result.highlight)

  const cite = async () => {
    try {
      await navigator.clipboard?.writeText(`${result.title} — ${result.url}`)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard blocked (no permission / insecure context) — leave the label as-is */
    }
  }

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-line px-6 py-4">
        <div className="flex items-center gap-2">
          <SourceBadge type={result.source_type} />
          {result.fresh && <span className="font-mono text-[10px] text-ok">● fresh</span>}
        </div>
        <h2 className="mt-2 text-base text-ink">{result.title}</h2>
        <a
          href={result.url}
          target="_blank"
          rel="noreferrer"
          className="mt-0.5 block truncate font-mono text-[11px] text-dim hover:text-accent"
        >
          {result.url}
        </a>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] text-muted">
          {result.org && <span>org · {result.org}</span>}
          <span>type · {result.source_type}</span>
          {result.published_at && <span>published · {result.published_at}</span>}
          <span>score · {result.score.toFixed(3)}</span>
          <span>rank · #{result.rank}</span>
        </div>
      </header>

      <div className="flex items-center justify-between border-b border-line-2 px-6 py-2">
        <div className="flex overflow-hidden rounded-md border border-line font-mono text-[10px]">
          {(['highlighted', 'full'] as Scope[]).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setScope(s)}
              className={`px-2.5 py-1 capitalize transition-colors ${
                scope === s ? 'text-on-accent' : 'text-muted hover:bg-hover'
              }`}
              style={scope === s ? { background: 'var(--color-accent)' } : undefined}
            >
              {s === 'full' ? 'Full-context' : 'Highlighted'}
            </button>
          ))}
        </div>
      </div>

      <article className="min-h-0 flex-1 overflow-auto px-6 py-5">
        <p
          className="text-sm leading-7 text-ink"
          dangerouslySetInnerHTML={{ __html: body }}
        />
      </article>

      <footer className="flex items-center gap-2 border-t border-line px-6 py-3 font-mono text-[11px]">
        <button
          type="button"
          disabled
          title="Phase 3 — entity search"
          className="rounded border border-line-2 px-2 py-1 text-dim opacity-50"
        >
          ＋ Add to entity table
        </button>
        <a
          href={result.url}
          target="_blank"
          rel="noreferrer"
          className="rounded border border-line px-2 py-1 text-muted hover:bg-hover"
        >
          ⧉ Open source
        </a>
        <button
          type="button"
          onClick={cite}
          title="Copy citation (title — URL) to clipboard"
          className={`rounded border px-2 py-1 transition-colors ${
            copied ? 'border-ok text-ok' : 'border-line text-muted hover:bg-hover'
          }`}
        >
          {copied ? '✓ Copied' : '❝ Cite'}
        </button>
      </footer>
    </div>
  )
}
