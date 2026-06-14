import { useState } from 'react'
import { Rail, type ViewId } from './app/Rail'
import { HealthPill } from './components/HealthPill'
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

export default function App() {
  const [view, setView] = useState<ViewId>('search')

  return (
    <div className="flex h-full">
      <Rail active={view} onSelect={setView} chunkCount={null} />
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-line bg-panel px-5 py-2">
          <span className="font-mono text-xs tracking-wide text-muted">
            noscia / {TITLES[view]}
          </span>
          <HealthPill />
        </header>
        <div className="min-h-0 flex-1">
          {view === 'search' && <Search />}
          {view === 'entity' && <EntitySearch />}
          {view === 'corpus' && <Corpus />}
          {view === 'settings' && <Settings />}
        </div>
      </main>
    </div>
  )
}
