// Live backend status pill — proves the end-to-end HTTP + DB path (SPEC §7 Phase 0).
// Polls /health; green when status==ok (DB reachable), amber degraded, red unreachable.
import { useEffect, useState } from 'react'
import { api, type HealthResponse } from '../lib/api'

type State =
  | { kind: 'loading' }
  | { kind: 'up'; data: HealthResponse }
  | { kind: 'down' }

export function HealthPill() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const data = await api.health()
        if (alive) setState({ kind: 'up', data })
      } catch {
        if (alive) setState({ kind: 'down' })
      }
    }
    poll()
    const id = setInterval(poll, 10_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  const { dot, label } = pillProps(state)
  return (
    <div
      className="flex items-center gap-2 rounded-full border border-line bg-panel-2 px-3 py-1 font-mono text-[11px] text-muted"
      title="backend /health"
    >
      <span className="inline-block h-2 w-2 rounded-full" style={{ background: dot }} />
      {label}
    </div>
  )
}

function pillProps(state: State): { dot: string; label: string } {
  switch (state.kind) {
    case 'loading':
      return { dot: 'var(--color-dim)', label: 'connecting…' }
    case 'down':
      return { dot: 'var(--color-accent-2)', label: 'backend offline' }
    case 'up':
      return state.data.db
        ? { dot: 'var(--color-ok)', label: `online · v${state.data.version}` }
        : { dot: 'var(--color-warn)', label: 'degraded · no db' }
  }
}
