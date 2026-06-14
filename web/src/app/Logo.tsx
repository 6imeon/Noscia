// Noscia mark — "Neural-N": the letter N drawn as a node-edge graph (the neural /
// embedding retrieval made visible). Bare, themeable mark: edges + corner ring nodes
// in --color-accent, a highlighted central hub, dark corner nodes in --color-ink. Colors
// come from the theme tokens so it follows the active palette. The favicon (public/
// favicon.svg) is the same mark on a warm dark app-icon tile.
export function Logo({ size = 22, className }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      className={className}
      role="img"
      aria-label="Noscia"
    >
      <g stroke="var(--color-accent)" strokeWidth="2.6" strokeLinecap="round">
        <line x1="13" y1="36" x2="13" y2="12" />
        <line x1="13" y1="12" x2="35" y2="36" />
        <line x1="35" y1="36" x2="35" y2="12" />
      </g>
      <g fill="var(--color-ink)">
        <circle cx="13" cy="12" r="3.6" />
        <circle cx="13" cy="36" r="3.6" />
        <circle cx="35" cy="12" r="3.6" />
        <circle cx="35" cy="36" r="3.6" />
      </g>
      <circle cx="24" cy="24" r="3.4" fill="var(--color-accent)" />
    </svg>
  )
}
