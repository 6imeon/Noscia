// Settings · BYOK (Phase 0 deliverable) — provider cards reflecting what's set in
// .env. Keys are read server-side via get_secret(); the browser only ever sees a
// masked confirmation (SPEC §2 rule 4 / §8.4).
import { useEffect, useState } from 'react'
import { api, type ProvidersResponse } from '../lib/api'

export function Settings() {
  const [data, setData] = useState<ProvidersResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .providers()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'failed to load'))
  }, [])

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="mb-1 text-lg text-ink">Settings · BYOK</h1>
      <p className="mb-5 text-sm text-muted">
        Provider keys load from <code className="font-mono text-dim">.env</code>. The browser
        never sees a raw key — only a masked confirmation.
      </p>

      {error ? <p className="text-sm text-accent-2">Couldn’t load providers — {error}</p> : null}
      {!data && !error ? <p className="text-sm text-dim">Loading…</p> : null}

      <div className="space-y-3">
        {data?.providers.map((p) => (
          <div
            key={p.provider}
            className="flex items-center justify-between rounded-md border border-line bg-panel p-4"
          >
            <div>
              <div className="flex items-center gap-2 text-sm capitalize text-ink">
                {p.provider}
                {p.provider === data.default_provider ? (
                  <span className="rounded border border-line px-1.5 py-0.5 font-mono text-[10px] text-dim">
                    default
                  </span>
                ) : null}
              </div>
              <div className="mt-1 font-mono text-xs text-muted">
                {p.configured ? (
                  <span style={{ color: 'var(--color-ok)' }}>● loaded from .env</span>
                ) : (
                  <span className="text-dim">not set — add to .env</span>
                )}
              </div>
            </div>
            <div className="font-mono text-xs text-dim">{p.masked || '—'}</div>
          </div>
        ))}
      </div>

      <p className="mt-6 rounded-md border border-line-2 bg-panel-2 p-3 font-mono text-[11px] text-dim">
        Dependency policy: pnpm <code>minimumReleaseAge: 10080</code> (7-day release cooldown).
      </p>
    </div>
  )
}
