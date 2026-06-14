// One result in the left list (§8.4): #rank · source badge · score bar · title ·
// org · host · highlighted snippet. The highlight HTML is backend-escaped before
// <mark> spans are inserted (server highlight.py), so dangerouslySetInnerHTML is safe.
import type { SearchResult } from '../lib/api'
import { ScoreBar } from './ScoreBar'
import { SourceBadge } from './SourceType'

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

export function ResultRow({
  result,
  active,
  onSelect,
}: {
  result: SearchResult
  active: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`block w-full border-b border-line-2 px-4 py-3 text-left transition-colors ${
        active ? 'bg-sel' : 'hover:bg-hover'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] text-dim">#{result.rank}</span>
        <SourceBadge type={result.source_type} />
        <ScoreBar score={result.score} />
        {result.fresh && <span className="ml-auto font-mono text-[10px] text-ok">● fresh</span>}
      </div>
      <div className="mt-1.5 truncate text-sm text-ink">{result.title}</div>
      <div className="truncate font-mono text-[10px] text-dim">
        {result.org ? `${result.org} · ` : ''}
        {host(result.url)}
      </div>
      <p
        className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-muted"
        dangerouslySetInnerHTML={{ __html: result.highlight }}
      />
    </button>
  )
}
