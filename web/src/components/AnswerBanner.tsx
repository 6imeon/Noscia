// Synthesized answer panel (top half of the right pane): one query-focused answer,
// grounded in the retrieved passages, with inline [n] citations that open the cited
// source in the passage reader below. Shown only when AI answers ran (summarized) and a
// key was configured; otherwise a muted hint. When the corpus doesn't answer, we say so
// honestly rather than invent (rule 8).
import type { SearchResponse, SearchResult } from '../lib/api'

// Split the answer on [n] markers so each citation renders as a clickable chip.
function renderWithCitations(
  text: string,
  results: SearchResult[],
  onSelect: (r: SearchResult) => void,
) {
  return text.split(/(\[\d+\])/g).map((part, i) => {
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
        className="mx-0.5 rounded bg-accent/15 px-1 align-super font-mono text-[9px] text-accent hover:bg-accent/30 disabled:opacity-50"
      >
        {rank}
      </button>
    )
  })
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full flex-col bg-accent/5">
      <div className="border-b border-line px-5 py-2 font-mono text-[10px] uppercase tracking-wide text-accent">
        ✦ Answer
        <span className="ml-1 text-dim normal-case tracking-normal">
          · synthesized from the cited passages
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-5 py-3">{children}</div>
    </div>
  )
}

export function AnswerBanner({
  data,
  onSelect,
  keyConfigured,
}: {
  data: SearchResponse
  onSelect: (r: SearchResult) => void
  keyConfigured: boolean
}) {
  if (!data.summarized)
    return (
      <Shell>
        <p className="text-sm text-dim">
          {keyConfigured
            ? 'Turn on ✦ AI answers to synthesize a direct answer here.'
            : 'Add a reasoning key in Settings · BYOK to get AI answers.'}
        </p>
      </Shell>
    )

  return (
    <Shell>
      {data.answer ? (
        <p className="text-sm leading-6 text-ink">
          {renderWithCitations(data.answer, data.results, onSelect)}
        </p>
      ) : (
        <p className="text-sm leading-6 text-muted">
          No direct answer in the corpus for this query — see the cited passages below.
        </p>
      )}
    </Shell>
  )
}
