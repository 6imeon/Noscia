// Left icon rail (62px) — logo, view switcher, Settings pinned bottom,
// vertical chunk count at the very bottom (SPEC §8.3).
import { Logo } from './Logo'

export type ViewId = 'search' | 'entity' | 'corpus' | 'settings'

const NAV: { id: ViewId; glyph: string; label: string }[] = [
  { id: 'search', glyph: '⌕', label: 'Search' },
  { id: 'entity', glyph: '▦', label: 'Entity search' },
  { id: 'corpus', glyph: '▤', label: 'Corpus & index' },
]

function RailButton({
  glyph,
  label,
  active,
  onClick,
}: {
  glyph: string
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-current={active}
      onClick={onClick}
      className={`group relative flex h-10 w-10 items-center justify-center rounded-md text-lg transition-colors ${
        active ? 'text-accent' : 'text-dim hover:text-muted hover:bg-hover'
      }`}
      style={active ? { background: 'var(--accent-soft)' } : undefined}
    >
      {glyph}
    </button>
  )
}

export function Rail({
  active,
  onSelect,
  chunkCount,
}: {
  active: ViewId
  onSelect: (v: ViewId) => void
  chunkCount: number | null
}) {
  return (
    <nav className="flex w-[62px] shrink-0 flex-col items-center gap-1 border-r border-line bg-rail py-3">
      <div
        className="mb-3 flex h-8 w-8 items-center justify-center rounded-md bg-accent/15"
        title="Noscia"
      >
        <Logo size={22} />
      </div>
      {NAV.map((n) => (
        <RailButton
          key={n.id}
          glyph={n.glyph}
          label={n.label}
          active={active === n.id}
          onClick={() => onSelect(n.id)}
        />
      ))}
      <div className="mt-auto flex flex-col items-center gap-3">
        <RailButton
          glyph="⚙"
          label="Settings"
          active={active === 'settings'}
          onClick={() => onSelect('settings')}
        />
        <span
          className="font-mono text-[10px] text-dim"
          style={{ writingMode: 'vertical-rl' }}
          title="chunks indexed"
        >
          {chunkCount === null ? '—' : `idx ${chunkCount.toLocaleString()}`}
        </span>
      </div>
    </nav>
  )
}
