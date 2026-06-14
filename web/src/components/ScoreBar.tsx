// Rerank/similarity score as a thin accent bar + numeric value (§8.4 result header).
export function ScoreBar({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score)) * 100
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1 w-10 overflow-hidden rounded-full bg-line-2">
        <div className="h-full" style={{ width: `${pct}%`, background: 'var(--color-accent)' }} />
      </div>
      <span className="font-mono text-[10px] text-muted">{score.toFixed(2)}</span>
    </div>
  )
}
