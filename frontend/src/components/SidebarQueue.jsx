import { useRef, useState } from 'react'
import { Loader2, ShieldAlert, ShieldCheck, Upload } from 'lucide-react'
import { riskLevel } from '../lib/redact'

const RISK_STYLE = {
  CRITICAL: 'border-rose-500/50 bg-rose-500/10 text-rose-400',
  MODERATE: 'border-amber-500/50 bg-amber-500/10 text-amber-400',
  CLEAN: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400',
}
const FILTERS = [
  ['ALL', 'All'],
  ['GOV_ID', 'Gov IDs'],
  ['FINANCIAL', 'Financial'],
  ['CONTACT_PII', 'Contact PII'],
]

export default function SidebarQueue({
  session, entities, customCount, filter, onFilter, busy, onUpload,
  onSelectAll, onDeselectAll, onClearCustom,
}) {
  const input = useRef(null)
  const [drag, setDrag] = useState(false)
  const risk = riskLevel(entities)
  const RiskIcon = risk === 'CLEAN' ? ShieldCheck : ShieldAlert

  const drop = (ev) => {
    ev.preventDefault()
    setDrag(false)
    const f = ev.dataTransfer.files[0]
    if (f) onUpload(f)
  }

  return (
    <aside className="flex min-h-0 flex-col gap-4 overflow-y-auto border-r border-zinc-800 bg-zinc-900/90 p-4">
      <div
        onClick={() => input.current.click()}
        onDragOver={(ev) => {
          ev.preventDefault()
          setDrag(true)
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={drop}
        className={`cursor-pointer rounded-lg border-2 border-dashed p-5 text-center transition ${drag ? 'border-cyan-400 bg-cyan-400/10' : 'border-zinc-700 hover:border-zinc-500'}`}
      >
        {busy === 'analyze' ? <Loader2 className="mx-auto mb-2 animate-spin text-cyan-400" /> : <Upload className="mx-auto mb-2 text-zinc-400" />}
        <p className="text-sm font-medium">{busy === 'analyze' ? 'Scanning document…' : 'Drop a dossier or click to upload'}</p>
        <p className="mt-1 font-mono text-[11px] text-zinc-500">.txt  .pdf  .png  .jpg</p>
        <input
          ref={input}
          type="file"
          hidden
          accept=".txt,.pdf,.png,.jpg,.jpeg"
          onChange={(ev) => {
            if (ev.target.files[0]) onUpload(ev.target.files[0])
            ev.target.value = ''
          }}
        />
      </div>

      {session && (
        <>
          <section className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-zinc-500">Risk Telemetry</h3>
            <p className="truncate text-sm" title={session.filename}>{session.filename}</p>
            <div className="mt-3 flex items-center justify-between">
              <div>
                <div className="font-mono text-3xl font-bold">{entities.length}</div>
                <div className="text-xs text-zinc-500">sensitive findings</div>
              </div>
              <span className={`flex items-center gap-1 rounded border px-2 py-1 font-mono text-xs font-bold ${RISK_STYLE[risk]}`}>
                <RiskIcon size={14} /> {risk}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {FILTERS.map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => onFilter(id)}
                  className={`rounded-full border px-2.5 py-1 text-xs transition ${filter === id ? 'border-zinc-300 bg-zinc-200 text-zinc-900' : 'border-zinc-700 text-zinc-400 hover:border-zinc-500'}`}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="mt-3 break-all font-mono text-[10px] text-zinc-500">SHA-256 {session.sha256_original}</p>
          </section>

          <section className="flex flex-col gap-2">
            <h3 className="text-[11px] font-semibold uppercase tracking-widest text-zinc-500">Bulk Actions</h3>
            <button onClick={onSelectAll} className="rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800">Select All Entities</button>
            <button onClick={onDeselectAll} className="rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800">Deselect All</button>
            <button onClick={onClearCustom} disabled={customCount === 0} className="rounded border border-zinc-700 px-3 py-2 text-sm hover:bg-zinc-800 disabled:opacity-40">
              Clear Custom Boxes ({customCount})
            </button>
          </section>
        </>
      )}
    </aside>
  )
}
