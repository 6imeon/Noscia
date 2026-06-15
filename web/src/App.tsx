import { useCallback, useEffect, useState } from 'react'
import { Rail, type ViewId } from './app/Rail'
import { IndustryProvider, INDUSTRY_KEY } from './app/industry'
import { IndustrySetup } from './app/IndustrySetup'
import { HealthPill } from './components/HealthPill'
import { api, DEFAULT_INDUSTRY, type Industry } from './lib/api'
import { Search } from './views/Search'
import { EntitySearch } from './views/EntitySearch'
import { Corpus } from './views/Corpus'
import { Settings } from './views/Settings'

const TITLES: Record<ViewId, string> = {
  search: 'Search',
  entity: 'Entity search',
  corpus: 'Corpus & index',
  settings: 'Settings',
}

// First-run boot: 'loading' while we ask the server which vertical is active, then 'gate'
// (show the setup menu — no vertical loaded/chosen) or 'app'. A returning user with a
// localStorage choice skips straight to 'app' (the server pref stays source of truth).
type Boot = 'loading' | 'gate' | 'app'

export default function App() {
  const [view, setView] = useState<ViewId>('search')

  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(INDUSTRY_KEY) : null
  const [activeIndustry, setActiveIndustry] = useState(stored ?? DEFAULT_INDUSTRY)
  const [industries, setIndustries] = useState<Industry[]>([])
  const [boot, setBoot] = useState<Boot>(stored ? 'app' : 'loading')
  const [pickerOpen, setPickerOpen] = useState(false)

  const refreshIndustries = useCallback(async () => {
    try {
      return await api.industries()
    } catch {
      return null
    }
  }, [])

  // Resolve the active vertical on mount. Degrade to the app (never trap behind the gate)
  // if the catalog is unavailable or empty — the backend still defaults every call to esg.
  useEffect(() => {
    let alive = true
    void (async () => {
      const res = await refreshIndustries()
      if (!alive) return
      const list = res?.industries ?? []
      setIndustries(list)
      if (list.length === 0) {
        setBoot('app')
        return
      }
      if (stored) {
        setBoot('app') // returning user — keep their choice, list is just for the switcher
        return
      }
      const activeEntry = list.find((i) => i.id === res!.active)
      setActiveIndustry(res!.active)
      setBoot(activeEntry?.loaded ? 'app' : 'gate')
    })()
    return () => {
      alive = false
    }
  }, [refreshIndustries, stored])

  const enter = useCallback(
    (id: string) => {
      setActiveIndustry(id)
      setPickerOpen(false)
      setBoot('app')
      void refreshIndustries().then((res) => res && setIndustries(res.industries))
    },
    [refreshIndustries],
  )

  if (boot === 'loading')
    return (
      <div className="flex h-full items-center justify-center text-sm text-dim">Loading…</div>
    )

  if (boot === 'gate')
    return <IndustrySetup industries={industries} active={activeIndustry} onChosen={enter} />

  const activeLabel = industries.find((i) => i.id === activeIndustry)?.label ?? activeIndustry

  return (
    <IndustryProvider value={{ activeIndustry, industries, openPicker: () => setPickerOpen(true) }}>
      <div className="flex h-full">
        <Rail active={view} onSelect={setView} chunkCount={null} />
        <main className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-line bg-panel px-5 py-2">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs tracking-wide text-muted">
                noscia / {TITLES[view]}
              </span>
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                title="Switch field"
                className="rounded border border-line px-2 py-0.5 font-mono text-[11px] text-muted transition-colors hover:border-accent/60 hover:text-accent"
              >
                {activeLabel} ▾
              </button>
            </div>
            <HealthPill />
          </header>
          {/* Keyed by the active vertical so switching clears each view's state (results,
              corpus listing) — no stale ESG rows lingering after a switch. */}
          <div className="min-h-0 flex-1" key={activeIndustry}>
            {view === 'search' && <Search />}
            {view === 'entity' && <EntitySearch />}
            {view === 'corpus' && <Corpus />}
            {view === 'settings' && <Settings />}
          </div>
        </main>
      </div>
      {pickerOpen && (
        <IndustrySetup
          industries={industries}
          active={activeIndustry}
          onChosen={enter}
          onCancel={() => setPickerOpen(false)}
        />
      )}
    </IndustryProvider>
  )
}
