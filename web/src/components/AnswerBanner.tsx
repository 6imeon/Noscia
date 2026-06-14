// Synthesized answer (§ Exa/Perplexity-style): one query-focused answer above the
// results, grounded in the retrieved passages, with inline [n] citations that jump to
// the cited row. Shown only when AI answers were requested AND a key was configured
// (summarized). When the corpus doesn't answer, we say so honestly rather than invent.
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

export function AnswerBanner({
  data,
  onSelect,
}: {
  data: SearchResponse
  onSelect: (r: SearchResult) => void
}) {
  // Not requested, or no key configured → no banner (the toggle communicates the key state).
  if (!data.summarized) return null

  return (
    <div className="border-b border-line bg-accent/5 px-5 py-3">
      <div className="mb-1 font-mono text-[10px] uppercase tracking-wide text-accent">
        ✦ Answer
        <span className="ml-1 text-dim normal-case tracking-normal">
          · synthesized from the cited passages
        </span>
      </div>
      {data.answer ? (
        <p className="max-h-40 overflow-auto text-sm leading-6 text-ink">
          {renderWithCitations(data.answer, data.results, onSelect)}
        </p>
      ) : (
        <p className="text-sm leading-6 text-muted">
          No direct answer in the corpus for this query — see the cited passages below.
        </p>
      )}
    </div>
  )
}
