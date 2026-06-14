// Shared top search bar + Quality/Fast tier toggle (SPEC §8.3–8.4).
import type { Tier } from '../lib/api'

export function SearchBar({
  value,
  onChange,
  onSubmit,
  tier,
  onTier,
  summarize = false,
  onSummarize,
  summarizeAvailable = false,
  placeholder = 'Search the ESG corpus…',
  busy = false,
}: {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  tier: Tier
  onTier: (t: Tier) => void
  summarize?: boolean
  onSummarize?: (v: boolean) => void
  summarizeAvailable?: boolean
  placeholder?: string
  busy?: boolean
}) {
  return (
    <div className="flex items-center gap-3">
      <form
        className="flex-1"
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit()
        }}
      >
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full rounded-md border border-line bg-field px-3 py-2 text-sm text-ink placeholder:text-dim focus:border-accent focus:outline-none"
        />
      </form>
      {onSummarize && (
        <button
          type="button"
          disabled={busy || !summarizeAvailable}
          onClick={() => onSummarize(!summarize)}
          title={
            summarizeAvailable
              ? 'Synthesize a query-focused answer per result (BYOK)'
              : 'Add a reasoning key in Settings · BYOK to enable AI answers'
          }
          className={`rounded-md border px-3 py-2 font-mono text-xs transition-colors disabled:opacity-40 ${
            summarize && summarizeAvailable
              ? 'border-accent text-bg'
              : 'border-line text-muted hover:bg-hover'
          }`}
          style={summarize && summarizeAvailable ? { background: 'var(--color-accent)' } : undefined}
        >
          ✦ AI answers
        </button>
      )}
      <TierToggle tier={tier} onTier={onTier} disabled={busy} />
    </div>
  )
}

export function TierToggle({
  tier,
  onTier,
  disabled = false,
}: {
  tier: Tier
  onTier: (t: Tier) => void
  disabled?: boolean
}) {
  return (
    <div className="flex overflow-hidden rounded-md border border-line font-mono text-xs">
      {(['quality', 'fast'] as Tier[]).map((t) => (
        <button
          key={t}
          type="button"
          disabled={disabled}
          onClick={() => onTier(t)}
          className={`px-3 py-2 capitalize transition-colors disabled:opacity-50 ${
            tier === t ? 'text-bg' : 'text-muted hover:bg-hover'
          }`}
          style={tier === t ? { background: 'var(--color-accent)' } : undefined}
        >
          {t}
        </button>
      ))}
    </div>
  )
}
