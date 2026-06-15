// The "Structured" tab body: the answer in typed, cited form (Exa-style). Same grounded
// retrieval as the prose Answer, but the output is fields → so the two tabs agree.
//
// AUTO (default): when you open the tab it extracts on its own — the model infers the
// salient fields from your question and fills them, so you never get a wall of blanks
// from a schema that doesn't fit. CUSTOM: pin your own fields (build-a-table use case)
// and hit Extract. Either way it's evidence-or-null per field (rule 8), and a paid BYOK
// call — so auto runs once per query (cached across tab switches) and custom waits for
// an explicit Extract rather than firing on every keystroke.
import { useEffect, useState } from 'react'
import {
  api,
  type ExtractedField,
  type SearchResult,
  type StructuredResponse,
  type Tier,
} from '../lib/api'
import { useIndustry } from '../app/industry'
import { CiteHosts, Sources } from './Citations'

type Field = { name: string; description: string }

// An optional starting template for the Custom editor — the facts you'd pull from a
// standard/target document. (Auto mode ignores this; it derives fields per query.)
const PRESET: Field[] = [
  { name: 'Target year', description: 'The net-zero or emissions target year' },
  { name: 'Scope coverage', description: 'Which emission scopes (1/2/3) are covered' },
  { name: 'Baseline year', description: 'The baseline year emissions are measured against' },
  { name: 'Standard cited', description: 'The framework or standard referenced' },
]

type Status =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'done'; data: StructuredResponse }

export function StructuredPanel({
  query,
  tier,
  keyConfigured,
  active,
  onSelect,
}: {
  query: string
  tier: Tier
  keyConfigured: boolean
  active: boolean // the Structured tab is the visible one — gate auto-extract on it
  onSelect: (r: SearchResult) => void
}) {
  const { activeIndustry } = useIndustry()
  const [fields, setFields] = useState<Field[]>([]) // empty ⇒ AUTO; non-empty ⇒ CUSTOM
  const [showEditor, setShowEditor] = useState(false)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const [prevQuery, setPrevQuery] = useState(query)

  // A new query invalidates any prior extraction — reset during render (the React-blessed
  // "adjust state on prop change" pattern) so we never show stale values. Back to idle then
  // lets the auto effect fire once for the new query (it guards on status.kind === 'idle').
  if (query !== prevQuery) {
    setPrevQuery(query)
    setStatus({ kind: 'idle' })
  }

  const valid = fields.filter((f) => f.name.trim())
  const custom = valid.length > 0

  const run = async (useFields: Field[]) => {
    if (!query.trim() || !keyConfigured) return
    setStatus({ kind: 'loading' })
    try {
      const data = await api.structured({
        query,
        tier,
        industry: activeIndustry,
        fields: useFields
          .filter((f) => f.name.trim())
          .map((f) => ({ name: f.name.trim(), description: f.description.trim() })),
      })
      setStatus({ kind: 'done', data })
    } catch (e) {
      setStatus({ kind: 'error', message: e instanceof Error ? e.message : 'extraction failed' })
    }
  }

  // Auto-extract once per query when the tab is first viewed — no click needed. Skipped in
  // Custom mode (a pinned schema waits for an explicit Extract). Kicking off an async fetch
  // with a loading state is a legitimate effect; the disables below cover exactly that.
  useEffect(() => {
    if (!active || custom || !keyConfigured || !query.trim()) return
    if (status.kind !== 'idle') return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void run([])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, custom, keyConfigured, query, status.kind])

  const setField = (i: number, patch: Partial<Field>) =>
    setFields((fs) => fs.map((f, j) => (j === i ? { ...f, ...patch } : f)))
  const addField = () => {
    setShowEditor(true)
    setFields((fs) => [...fs, { name: '', description: '' }])
  }
  const removeField = (i: number) => setFields((fs) => fs.filter((_, j) => j !== i))
  const backToAuto = () => {
    setFields([])
    setShowEditor(false)
    setStatus({ kind: 'idle' }) // idle ⇒ the auto effect re-fires for this query
  }

  if (!query.trim())
    return <p className="text-sm text-dim">Run a search, then extract structured fields from it.</p>

  if (!keyConfigured)
    return (
      <p className="text-xs text-dim">
        Structured extraction needs a reasoning key — add one in Settings · BYOK.
      </p>
    )

  return (
    <div>
      {/* mode + actions toolbar */}
      <div className="flex items-center gap-3 font-mono text-[11px]">
        <span className="text-dim">
          {custom ? 'Custom fields' : 'Auto · fields inferred from your question'}
        </span>
        <button
          type="button"
          disabled={status.kind === 'loading' || (custom && valid.length === 0)}
          onClick={() => run(custom ? valid : [])}
          className="text-muted transition-colors hover:text-accent disabled:cursor-not-allowed disabled:text-dim"
        >
          {status.kind === 'loading' ? 'Extracting…' : '↻ Re-extract'}
        </button>
        <button
          type="button"
          onClick={() => setShowEditor((s) => !s)}
          className="ml-auto text-muted transition-colors hover:text-accent"
        >
          {showEditor ? '× Close editor' : '⊞ Customize fields'}
        </button>
      </div>

      {showEditor && (
        <div className="mt-3 rounded-lg border border-line-2 bg-panel/40 p-3">
          <div className="space-y-2">
            {fields.map((f, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  value={f.name}
                  onChange={(e) => setField(i, { name: e.target.value })}
                  placeholder="field name"
                  className="w-40 shrink-0 rounded-md border border-line bg-field px-2 py-1.5 text-xs text-ink placeholder:text-dim focus:border-accent focus:outline-none"
                />
                <input
                  value={f.description}
                  onChange={(e) => setField(i, { description: e.target.value })}
                  placeholder="what to extract (optional)"
                  className="min-w-0 flex-1 rounded-md border border-line bg-field px-2 py-1.5 text-xs text-ink placeholder:text-dim focus:border-accent focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => removeField(i)}
                  title="Remove field"
                  className="shrink-0 px-1 text-dim transition-colors hover:text-accent-2"
                >
                  ✕
                </button>
              </div>
            ))}
            {fields.length === 0 && (
              <p className="text-xs text-dim">
                Add fields to pin a fixed schema, or load the ESG preset. Leave empty to stay on Auto.
              </p>
            )}
          </div>

          <div className="mt-3 flex items-center gap-3 font-mono text-[11px]">
            <button type="button" onClick={addField} className="text-muted transition-colors hover:text-accent">
              + Add field
            </button>
            <button
              type="button"
              onClick={() => {
                setShowEditor(true)
                setFields(PRESET)
              }}
              className="text-muted transition-colors hover:text-accent"
            >
              ↺ ESG preset
            </button>
            {custom && (
              <button type="button" onClick={backToAuto} className="text-muted transition-colors hover:text-accent">
                ✦ Back to Auto
              </button>
            )}
            <button
              type="button"
              disabled={valid.length === 0 || status.kind === 'loading'}
              onClick={() => run(valid)}
              className="ml-auto rounded-md border border-accent bg-accent px-3 py-1.5 text-xs text-on-accent transition-colors disabled:cursor-not-allowed disabled:border-line disabled:bg-transparent disabled:text-dim"
            >
              {status.kind === 'loading' ? 'Extracting…' : '⊞ Extract'}
            </button>
          </div>
        </div>
      )}

      {/* results */}
      {status.kind === 'loading' && (
        <div className="mt-4 space-y-1.5">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-9 animate-pulse rounded-md bg-panel-2" />
          ))}
        </div>
      )}
      {status.kind === 'error' && (
        <p className="mt-4 text-sm text-accent-2">Extraction failed — {status.message}</p>
      )}
      {status.kind === 'done' && <Result data={status.data} onSelect={onSelect} />}
    </div>
  )
}

function Result({
  data,
  onSelect,
}: {
  data: StructuredResponse
  onSelect: (r: SearchResult) => void
}) {
  if (!data.extracted)
    return (
      <p className="mt-4 text-xs text-dim">
        No reasoning key configured — add one in Settings · BYOK to extract.
      </p>
    )
  if (data.fields.length === 0)
    return (
      <p className="mt-4 text-xs text-dim">
        Nothing extractable from these passages — try a more specific query, or pin custom fields.
      </p>
    )
  const allCitations = data.fields.flatMap((f) => f.citations)
  // The answer as a JSON object: snake_case keys, sentence values, source chips trailing
  // each value (Exa-style). Rendered as literal-looking JSON so it reads as structured data.
  return (
    <div className="mt-4">
      <div className="rounded-lg border border-line-2 bg-panel/40 px-4 py-3 font-mono text-[12.5px] leading-relaxed">
        <span className="text-dim">{'{'}</span>
        {data.fields.map((f, i) => (
          <Row
            key={i}
            field={f}
            results={data.results}
            onSelect={onSelect}
            last={i === data.fields.length - 1}
          />
        ))}
        <span className="text-dim">{'}'}</span>
      </div>
      <Sources citations={allCitations} results={data.results} onSelect={onSelect} />
    </div>
  )
}

// One "key": "value" line of the JSON object. Null values render as JSON `null`.
function Row({
  field,
  results,
  onSelect,
  last,
}: {
  field: ExtractedField
  results: SearchResult[]
  onSelect: (r: SearchResult) => void
  last: boolean
}) {
  return (
    <div className="py-1 pl-4">
      <span className="text-accent-2">{field.name}</span>
      <span className="text-dim">: </span>
      {field.value ? (
        <>
          <span className="text-ink">&ldquo;{field.value}&rdquo;</span>
          {!last && <span className="text-dim">,</span>}
          <CiteHosts citations={field.citations} results={results} onSelect={onSelect} />
        </>
      ) : (
        <>
          <span className="text-dim italic" title="Not found in the cited passages">
            null
          </span>
          {!last && <span className="text-dim">,</span>}
        </>
      )}
    </div>
  )
}
