import { Loader2 } from 'lucide-react'
import { CATEGORIES, MODES } from '../lib/theme'

export default function InspectorPanel({
  entities, filter, mode, onMode, stamp, onStamp, onToggle, onClone, busy, disabled, error, isText,
}) {
  const list = entities.filter((e) => filter === 'ALL' || e.category === filter)
  const selected = entities.filter((e) => e.selected_for_redaction).length

  return (
    <aside className="flex min-h-0 flex-col gap-4 border-l border-zinc-800 bg-zinc-900/90 p-4">
      <section>
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-zinc-500">Redaction Mode</h3>
        <div className="flex flex-col gap-2">
          {MODES.map((m) => (
            <label
              key={m.id}
              className={`cursor-pointer rounded-lg border p-3 transition ${mode === m.id ? 'border-cyan-400 bg-cyan-400/10' : 'border-zinc-800 hover:border-zinc-600'}`}
            >
              <input type="radio" name="mode" className="sr-only" checked={mode === m.id} onChange={() => onMode(m.id)} />
              <div className="text-sm font-medium">{m.title}</div>
              <div className="mt-0.5 text-xs text-zinc-400">{m.desc}</div>
            </label>
          ))}
        </div>
      </section>

      <button
        type="button"
        role="switch"
        aria-checked={stamp}
        onClick={() => onStamp(!stamp)}
        className="flex items-center justify-between gap-3 rounded-lg border border-zinc-800 p-3 text-left text-sm"
      >
        <span>Burn 'DECLASSIFIED // PII SCRUBBED' Watermark Stamp</span>
        <span className={`relative h-5 w-9 shrink-0 rounded-full transition ${stamp ? 'bg-rose-500' : 'bg-zinc-700'}`}>
          <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${stamp ? 'left-[18px]' : 'left-0.5'}`} />
        </span>
      </button>

      <section className="flex min-h-0 flex-1 flex-col">
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
          Detected Entities <span className="font-mono text-zinc-400">({selected}/{entities.length} selected)</span>
        </h3>
        <ul className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          {list.length === 0 && <li className="text-xs text-zinc-600">No findings to display.</li>}
          {list.map((e) => (
            <li key={e.id} className="rounded border border-zinc-800 bg-zinc-950/60 p-2">
              <label className="flex cursor-pointer items-start gap-2">
                <input type="checkbox" className="mt-1 accent-cyan-400" checked={e.selected_for_redaction} onChange={() => onToggle(e.id)} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className={`rounded border px-1.5 font-mono text-[10px] ${CATEGORIES[e.category].badge}`}>{e.entity_type}</span>
                    <span className="ml-auto font-mono text-[11px] text-zinc-400">{Math.round((e.score || 0) * 100)}%</span>
                  </div>
                  <div className="mt-1 truncate font-mono text-xs">{e.text}</div>
                  <div className="mt-1 flex items-center gap-2 font-mono text-[10px] text-zinc-500">
                    <span>{isText ? '' : `P${e.page_number} · `}L{e.line_number}</span>
                    {e.verified && <span className="rounded bg-emerald-500/15 px-1.5 text-emerald-400">{e.verified}</span>}
                  </div>
                </div>
              </label>
            </li>
          ))}
        </ul>
      </section>

      {error && <p className="rounded border border-rose-500/40 bg-rose-500/10 p-2 text-xs text-rose-300">{error}</p>}
      <button
        onClick={onClone}
        disabled={disabled}
        className="flex items-center justify-center gap-2 rounded-lg bg-rose-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy === 'clone' && <Loader2 size={16} className="animate-spin" />}
        Clone & Sanitize Document
      </button>
    </aside>
  )
}
