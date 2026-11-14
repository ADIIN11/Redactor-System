import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { CATEGORIES } from '../lib/theme'
import { base64ToBlob } from '../lib/api'

const clamp = (v) => Math.min(1, Math.max(0, v))
const PATTERN = 'repeating-linear-gradient(45deg, #09090b 0 6px, #18181b 6px 12px)'

function boxStyle(b) {
  return {
    left: `${b.x0 * 100}%`,
    top: `${b.y0 * 100}%`,
    width: `${(b.x1 - b.x0) * 100}%`,
    height: `${(b.y1 - b.y0) * 100}%`,
  }
}

function PreviewBar({ type, mode }) {
  if (type === 'CUSTOM_BOX' || mode === 'cia_blackout') {
    return <div className="bar-in h-full w-full border border-zinc-700" style={{ backgroundImage: PATTERN }} />
  }
  if (mode === 'entity_tag') {
    return (
      <div className="bar-in flex h-full w-full items-center justify-center overflow-hidden border border-cyan-400 bg-slate-800 font-mono text-[10px] text-white">
        [{type}]
      </div>
    )
  }
  if (type === 'IN_AADHAAR') {
    return (
      <div className="bar-in flex h-full w-full items-center justify-center overflow-hidden border border-zinc-700 bg-zinc-950 font-mono text-[9px] text-white">
        [AADHAAR REDACTED]
      </div>
    )
  }
  return (
    <div className="flex h-full w-full">
      <div className="bar-in h-full border border-zinc-700" style={{ width: '70%', backgroundImage: PATTERN }} />
    </div>
  )
}

export default function DocumentCanvas({
  page, entities, customBoxes, viewMode, mode, stamp, filter,
  onToggle, onAddBox, onRemoveBox, pageCount, onPage,
}) {
  const overlay = useRef(null)
  const [draft, setDraft] = useState(null)
  const [src, setSrc] = useState('')

  useEffect(() => {
    if (!page.preview_b64) return undefined
    const url = URL.createObjectURL(base64ToBlob(page.preview_b64, 'image/png'))
    setSrc(url)
    return () => URL.revokeObjectURL(url)
  }, [page.preview_b64])

  const xray = viewMode === 'xray'
  const shown = useMemo(
    () =>
      entities.filter((e) => e.bbox && e.page_number === page.page_number).filter((e) => {
        // The blackout preview always reflects the true export, regardless of filter
        return xray ? filter === 'ALL' || e.category === filter : e.selected_for_redaction
      }),
    [entities, page.page_number, xray, filter],
  )
  const customs = customBoxes.filter((b) => b.page_number === page.page_number)

  const point = (ev) => {
    const r = overlay.current.getBoundingClientRect()
    return { x: clamp((ev.clientX - r.left) / r.width), y: clamp((ev.clientY - r.top) / r.height) }
  }
  const down = (ev) => {
    if (ev.button !== 0) return
    ev.currentTarget.setPointerCapture(ev.pointerId)
    const p = point(ev)
    setDraft({ sx: p.x, sy: p.y, x: p.x, y: p.y })
  }
  const move = (ev) => {
    if (draft) setDraft({ ...draft, ...point(ev) })
  }
  const up = () => {
    if (!draft) return
    const bbox = {
      x0: Math.min(draft.sx, draft.x), y0: Math.min(draft.sy, draft.y),
      x1: Math.max(draft.sx, draft.x), y1: Math.max(draft.sy, draft.y),
    }
    setDraft(null)
    if (bbox.x1 - bbox.x0 > 0.005 && bbox.y1 - bbox.y0 > 0.003) onAddBox(page.page_number, bbox)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 overflow-auto p-6">
        <div className="relative mx-auto w-full max-w-4xl shadow-2xl shadow-black/60">
          {src && <img src={src} alt={`Page ${page.page_number}`} draggable={false} className="block w-full select-none" />}
          <div
            ref={overlay}
            className="absolute inset-0 cursor-crosshair touch-none"
            onPointerDown={down}
            onPointerMove={move}
            onPointerUp={up}
          >
            {shown.map((e) => {
              const c = CATEGORIES[e.category]
              return xray ? (
                <button
                  key={e.id}
                  type="button"
                  style={boxStyle(e.bbox)}
                  onPointerDown={(ev) => ev.stopPropagation()}
                  onClick={() => onToggle(e.id)}
                  title="Click to toggle redaction"
                  className={`absolute border-2 transition ${c.box} ${e.selected_for_redaction ? '' : 'border-dashed opacity-40'}`}
                >
                  <span className={`absolute -top-5 left-0 whitespace-nowrap rounded px-1 font-mono text-[10px] leading-4 ${c.pill}`}>
                    {e.entity_type} • {Math.round((e.score || 0) * 100)}%
                  </span>
                </button>
              ) : (
                <div key={e.id} style={boxStyle(e.bbox)} className="pointer-events-none absolute">
                  <PreviewBar type={e.entity_type} mode={mode} />
                </div>
              )
            })}
            {customs.map((b) =>
              xray ? (
                <button
                  key={b.id}
                  type="button"
                  style={boxStyle(b.bbox)}
                  onPointerDown={(ev) => ev.stopPropagation()}
                  onClick={() => onRemoveBox(b.id)}
                  title="Click to remove custom box"
                  className={`absolute border-2 ${CATEGORIES.CUSTOM_BOX.box}`}
                >
                  <span className={`absolute -top-5 left-0 rounded px-1 font-mono text-[10px] leading-4 ${CATEGORIES.CUSTOM_BOX.pill}`}>
                    CUSTOM_BOX
                  </span>
                </button>
              ) : (
                <div key={b.id} style={boxStyle(b.bbox)} className="pointer-events-none absolute">
                  <PreviewBar type="CUSTOM_BOX" mode={mode} />
                </div>
              ),
            )}
            {draft && (
              <div
                className="pointer-events-none absolute border-2 border-dashed border-emerald-500 bg-emerald-500/20"
                style={boxStyle({
                  x0: Math.min(draft.sx, draft.x), y0: Math.min(draft.sy, draft.y),
                  x1: Math.max(draft.sx, draft.x), y1: Math.max(draft.sy, draft.y),
                })}
              />
            )}
            {!xray && stamp && page.page_number === 1 && (
              <div className="pointer-events-none absolute right-[3%] top-[2%] rotate-12 border-2 border-red-700 bg-red-700/10 px-2 py-1 font-mono text-[10px] font-bold text-red-600/80">
                REDACTED CLONE // ZERO-LEAK VERIFIED
              </div>
            )}
          </div>
        </div>
        <p className="mt-3 text-center text-xs text-zinc-500">
          Drag anywhere on the page to draw a custom redaction box
        </p>
      </div>
      <div className="flex items-center justify-center gap-4 border-t border-zinc-800 bg-zinc-900/90 py-2 font-mono text-xs">
        <button disabled={page.page_number <= 1} onClick={() => onPage(page.page_number - 1)} className="rounded p-1 hover:bg-zinc-800 disabled:opacity-30">
          <ChevronLeft size={16} />
        </button>
        <span>Page {page.page_number} of {pageCount}</span>
        <button disabled={page.page_number >= pageCount} onClick={() => onPage(page.page_number + 1)} className="rounded p-1 hover:bg-zinc-800 disabled:opacity-30">
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  )
}
