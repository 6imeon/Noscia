// Source-type badge + dot. The §8.2 color system is the single source of truth:
// backend returns a `source_type` string, we map it to the matching CSS token
// (--color-framework … --color-news, which share the literal's name). Tints use
// color-mix so one token drives fill + border (10–12% fill / ~38% border).
import type { SourceType } from '../lib/api'

function typeVar(type: SourceType): string {
  return `var(--color-${type})`
}

export function SourceBadge({ type }: { type: SourceType }) {
  const c = typeVar(type)
  return (
    <span
      className="rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide"
      style={{
        color: c,
        background: `color-mix(in srgb, ${c} 12%, transparent)`,
        border: `1px solid color-mix(in srgb, ${c} 38%, transparent)`,
      }}
    >
      {type}
    </span>
  )
}

export function SourceDot({ type }: { type: SourceType }) {
  return (
    <span
      className="inline-block h-2 w-2 shrink-0 rounded-full"
      style={{ background: typeVar(type) }}
      title={type}
    />
  )
}
