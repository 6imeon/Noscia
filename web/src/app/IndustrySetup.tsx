// The setup menu (first run) and the switcher (later) — one component, two entries.
// Pick a field → POST /industries/select. If that vertical isn't crawled yet, kick off
// its first ingest and show a "building your corpus" state, then drop into the app. A
// vertical that's already `loaded` switches instantly (Model A — no recrawl).
import { useState } from 'react'
import { api, type Industry } from '../lib/api'
import { INDUSTRY_KEY } from './industry'

type Phase =
  | { kind: 'idle' }
  | { kind: 'building'; id: string } // first crawl of a not-yet-loaded vertical
  | { kind: 'error'; message: string }

export function IndustrySetup({
  industries,
  active,
  onChosen,
  onCancel,
}: {
  industries: Industry[]
  active: string
  onChosen: (id: string) => void
  // Present only when invoked as the switcher (first-run setup can't be dismissed).
  onCancel?: () => void
}) {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })

  const choose = async (id: string) => {
    if (phase.kind === 'building') return
    setPhase({ kind: 'idle' })
    try {
      const res = await api.selectIndustry(id)
      const chosen = res.industries.find((i) => i.id === id)
      if (chosen && !chosen.loaded) {
        // First load of this vertical: crawl its seeds before entering. Synchronous for
        // the demo (like the Corpus recrawl); live progress streaming is later work.
        setPhase({ kind: 'building', id })
        await api.ingest({ industry: id })
      }
      localStorage.setItem(INDUSTRY_KEY, id)
      onChosen(id)
    } catch (e) {
      setPhase({ kind: 'error', message: e instanceof Error ? e.message : 'could not load that field' })
    }
  }

  const building = phase.kind === 'building'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/95 p-6">
      <div className="w-full max-w-2xl">
        <div className="mb-1 flex items-center gap-3">
          <h1 className="text-lg text-ink">Choose a field</h1>
          {onCancel && !building && (
            <button
              type="button"
              onClick={onCancel}
              className="ml-auto font-mono text-[11px] text-dim transition-colors hover:text-muted"
            >
              ✕ cancel
            </button>
          )}
        </div>
        <p className="mb-5 text-sm text-dim">
          Noscia searches one curated vertical at a time. Pick the field you want — it loads
          its authoritative sources, and you can switch later.
        </p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {industries.map((ind) => {
            const isActive = ind.id === active
            const isBuilding = building && phase.id === ind.id
            return (
              <button
                key={ind.id}
                type="button"
                disabled={building}
                onClick={() => choose(ind.id)}
                className={`rounded-lg border p-4 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                  isActive ? 'border-accent bg-accent/10' : 'border-line bg-panel hover:border-accent/60 hover:bg-hover'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-base text-accent">{glyph(ind.icon)}</span>
                  <span className="text-ink">{ind.label}</span>
                  {ind.loaded ? (
                    <span className="ml-auto font-mono text-[9px] uppercase tracking-wide text-ok">
                      ready
                    </span>
                  ) : (
                    <span className="ml-auto font-mono text-[9px] uppercase tracking-wide text-dim">
                      builds on first use
                    </span>
                  )}
                </div>
                <p className="mt-2 text-xs text-dim">{ind.blurb}</p>
                {isBuilding && (
                  <p className="mt-2 animate-pulse font-mono text-[10px] text-warn">
                    building corpus — crawling sources…
                  </p>
                )}
              </button>
            )
          })}
        </div>

        {phase.kind === 'error' && (
          <p className="mt-4 font-mono text-[11px] text-accent-2">{phase.message}</p>
        )}
        {building && (
          <p className="mt-4 text-xs text-dim">
            First load crawls the field's sources — this can take a minute. Leave this open.
          </p>
        )}
      </div>
    </div>
  )
}

// Minimal icon mapping — the catalog `icon` is a free-form slug for now.
function glyph(icon: string): string {
  const map: Record<string, string> = {
    leaf: '🌱',
    chart: '📈',
    heart: '⚕',
    shield: '🛡',
    cpu: '◈',
    bolt: '⚡',
    bank: '🏦',
    wheat: '🌾',
    pill: '💊',
    rocket: '🚀',
  }
  return map[icon] ?? '◆'
}
