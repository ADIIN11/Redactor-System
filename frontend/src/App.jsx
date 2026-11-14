import { useMemo, useState } from 'react'
import { Scale } from 'lucide-react'
import SidebarQueue from './components/SidebarQueue'
import DocumentCanvas from './components/DocumentCanvas'
import TextTeleprinter from './components/TextTeleprinter'
import InspectorPanel from './components/InspectorPanel'
import AuditCertificateModal from './components/AuditCertificateModal'
import LicenseDisclosureModal from './components/LicenseDisclosureModal'
import { analyzeFile, cloneRedact, base64ToBlob, saveBlob } from './lib/api'
import { categoryOf } from './lib/theme'
import { verificationLabel } from './lib/redact'

export default function App() {
  const [session, setSession] = useState(null)
  const [entities, setEntities] = useState([])
  const [customBoxes, setCustomBoxes] = useState([])
  const [viewMode, setViewMode] = useState('xray')
  const [mode, setMode] = useState('cia_blackout')
  const [stamp, setStamp] = useState(true)
  const [filter, setFilter] = useState('ALL')
  const [pageNo, setPageNo] = useState(1)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [receipt, setReceipt] = useState(null)
  const [showLicenses, setShowLicenses] = useState(false)

  const isText = session && session.file_type === 'txt'
  const page = useMemo(
    () => (session ? session.pages.find((p) => p.page_number === pageNo) || session.pages[0] : null),
    [session, pageNo],
  )

  async function handleUpload(file) {
    setBusy('analyze')
    setError('')
    try {
      const res = await analyzeFile(file)
      setSession(res)
      setEntities(
        res.entities.map((e) => ({ ...e, category: categoryOf(e.entity_type), verified: verificationLabel(e) })),
      )
      setCustomBoxes([])
      setPageNo(1)
      setFilter('ALL')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const toggle = (id) =>
    setEntities((list) => list.map((e) => (e.id === id ? { ...e, selected_for_redaction: !e.selected_for_redaction } : e)))
  const setAll = (value) => setEntities((list) => list.map((e) => ({ ...e, selected_for_redaction: value })))
  const addBox = (page_number, bbox) =>
    setCustomBoxes((list) => [...list, { id: `custom_${Date.now()}_${list.length}`, page_number, bbox }])
  const removeBox = (id) => setCustomBoxes((list) => list.filter((b) => b.id !== id))

  async function handleClone() {
    setBusy('clone')
    setError('')
    try {
      const res = await cloneRedact({
        session_id: session.session_id,
        mode,
        add_declassified_stamp: stamp,
        entities: entities.map((e) => ({ id: e.id, selected_for_redaction: e.selected_for_redaction })),
        custom_boxes: customBoxes.map((b) => ({ page_number: b.page_number, bbox: b.bbox })),
      })
      saveBlob(base64ToBlob(res.file_b64, res.mime_type), res.output_filename)
      setReceipt(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const viewBtn = (id, label) => (
    <button
      onClick={() => setViewMode(id)}
      className={`rounded-full px-4 py-1.5 text-sm transition ${viewMode === id ? 'bg-zinc-100 text-zinc-900' : 'text-zinc-400 hover:text-zinc-200'}`}
    >
      {label}
    </button>
  )

  return (
    <div className="flex h-full flex-col bg-zinc-950">
      <header className="flex items-center justify-between gap-4 border-b border-zinc-800 bg-zinc-900/90 px-4 py-2">
        <h1 className="font-mono text-xs font-bold tracking-widest text-zinc-300">
          CB-02 // INTELLIGENT PII DETECTION & CIA REDACTION STUDIO
        </h1>
        <div className="flex gap-1 rounded-full border border-zinc-700 bg-zinc-950 p-1">
          {viewBtn('xray', '🔍 X-Ray Inspect Mode')}
          {viewBtn('blackout', '⬛ Live CIA Blackout Preview')}
        </div>
        <button onClick={() => setShowLicenses(true)} className="flex items-center gap-2 rounded border border-zinc-700 px-3 py-1.5 text-xs hover:bg-zinc-800">
          <Scale size={14} /> Open-Source Licenses (MIT/Apache-2.0)
        </button>
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-[300px_1fr_360px]">
        <SidebarQueue
          session={session}
          entities={entities}
          customCount={customBoxes.length}
          filter={filter}
          onFilter={setFilter}
          busy={busy}
          onUpload={handleUpload}
          onSelectAll={() => setAll(true)}
          onDeselectAll={() => setAll(false)}
          onClearCustom={() => setCustomBoxes([])}
        />
        <section className="min-h-0 bg-zinc-950">
          {!session && (
            <div className="flex h-full items-center justify-center font-mono text-sm text-zinc-600">
              AWAITING CLASSIFIED DOCUMENT…
            </div>
          )}
          {session && isText && (
            <TextTeleprinter
              lines={page.raw_text_lines}
              entities={entities}
              viewMode={viewMode}
              mode={mode}
              stamp={stamp}
              filter={filter}
              onToggle={toggle}
            />
          )}
          {session && !isText && page && (
            <DocumentCanvas
              page={page}
              entities={entities}
              customBoxes={customBoxes}
              viewMode={viewMode}
              mode={mode}
              stamp={stamp}
              filter={filter}
              onToggle={toggle}
              onAddBox={addBox}
              onRemoveBox={removeBox}
              pageCount={session.page_count}
              onPage={setPageNo}
            />
          )}
        </section>
        <InspectorPanel
          entities={entities}
          filter={filter}
          mode={mode}
          onMode={setMode}
          stamp={stamp}
          onStamp={setStamp}
          onToggle={toggle}
          onClone={handleClone}
          busy={busy}
          disabled={!session || busy !== ''}
          error={error}
          isText={isText}
        />
      </main>

      {receipt && <AuditCertificateModal receipt={receipt} onClose={() => setReceipt(null)} />}
      {showLicenses && <LicenseDisclosureModal onClose={() => setShowLicenses(false)} />}
    </div>
  )
}
