// The grounded-output pane (top half of the right column): a tab bar over the same
// search — "Answer" (prose synthesis) and "Structured" (schema extraction). Both ground
// in the retrieved passages and cite the result rows; the tab chrome lives here so the
// two bodies stay visually consistent (cf. Exa's Answer / Structured tabs).
import { useState } from 'react'
import type { SearchResponse, SearchResult } from '../lib/api'
import { AnswerBody } from './AnswerBanner'
import { StructuredPanel } from './StructuredPanel'

type Tab = 'answer' | 'structured'

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`-mb-px border-b-2 px-1 pb-2 font-mono text-[10px] uppercase tracking-wide transition-colors ${
        active ? 'border-accent text-accent' : 'border-transparent text-dim hover:text-muted'
      }`}
    >
      {children}
    </button>
  )
}

export function OutputPane({
  data,
  onSelect,
  keyConfigured,
}: {
  data: SearchResponse
  onSelect: (r: SearchResult) => void
  keyConfigured: boolean
}) {
  const [tab, setTab] = useState<Tab>('answer')
  return (
    <div className="flex h-full flex-col bg-accent/5">
      <div className="flex items-center gap-4 border-b border-line px-5 pt-2">
        <TabButton active={tab === 'answer'} onClick={() => setTab('answer')}>
          ✦ Answer
        </TabButton>
        <TabButton active={tab === 'structured'} onClick={() => setTab('structured')}>
          ⊞ Structured
        </TabButton>
        <span className="ml-auto pb-2 font-mono text-[10px] text-dim">
          {tab === 'answer' ? 'synthesized from the cited passages' : 'the answer, as cited JSON'}
        </span>
      </div>
      {/* Both bodies stay mounted (toggled with `hidden`) so the Structured tab's
          auto-extraction isn't re-run — and re-charged — every time you flip tabs. */}
      <div className="min-h-0 flex-1 overflow-auto px-5 py-4">
        <div className={tab === 'answer' ? '' : 'hidden'}>
          <AnswerBody data={data} onSelect={onSelect} keyConfigured={keyConfigured} />
        </div>
        <div className={tab === 'structured' ? '' : 'hidden'}>
          <StructuredPanel
            query={data.query}
            tier={data.tier}
            keyConfigured={keyConfigured}
            active={tab === 'structured'}
            onSelect={onSelect}
          />
        </div>
      </div>
    </div>
  )
}
