// The "Answer" tab body (top half of the right pane): one query-focused answer,
// grounded in the retrieved passages, with inline [n] citations that open the cited
// source in the passage reader below — plus a Sources list of the cited results
// (badge · date · title · host). Shown only when AI answers ran (summarized) and a key
// was configured; otherwise a muted hint. When the corpus doesn't answer, we say so
// honestly rather than invent (rule 8). The tabbed chrome lives in OutputPane.
import type { SearchResponse, SearchResult } from '../lib/api'
import { CitedText, Sources } from './Citations'

export function AnswerBody({
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
      <p className="text-sm text-dim">
        {keyConfigured
          ? 'Turn on ✦ AI answers to synthesize a direct answer here.'
          : 'Add a reasoning key in Settings · BYOK to get AI answers.'}
      </p>
    )

  if (!data.answer)
    return (
      <p className="text-sm leading-6 text-muted">
        No direct answer in the corpus for this query — see the cited passages below.
      </p>
    )

  return (
    <>
      <p className="text-[15px] leading-7 text-ink">
        <CitedText text={data.answer} results={data.results} onSelect={onSelect} />
      </p>
      <Sources
        citations={data.answer_citations ?? []}
        results={data.results}
        onSelect={onSelect}
      />
    </>
  )
}
