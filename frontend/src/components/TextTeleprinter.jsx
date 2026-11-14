import { CATEGORIES } from '../lib/theme'
import { BANNER, textReplacement } from '../lib/redact'

function segments(text, ents) {
  const out = []
  let cur = 0
  ents
    .slice()
    .sort((a, b) => a.start_char - b.start_char)
    .forEach((e) => {
      if (e.start_char < cur) return
      if (e.start_char > cur) out.push({ t: text.slice(cur, e.start_char) })
      out.push({ t: text.slice(e.start_char, e.end_char), e })
      cur = e.end_char
    })
  if (cur < text.length) out.push({ t: text.slice(cur) })
  return out
}

export default function TextTeleprinter({ lines, entities, viewMode, mode, stamp, filter, onToggle }) {
  const xray = viewMode === 'xray'
  return (
    <div className="h-full overflow-auto p-6">
      <div className="mx-auto max-w-4xl rounded border border-zinc-800 bg-zinc-950 p-4 font-mono text-sm leading-6 shadow-2xl shadow-black/60">
        {!xray && stamp && (
          <pre className="mb-2 whitespace-pre-wrap border-b border-zinc-800 pb-2 text-red-500">{BANNER}</pre>
        )}
        {lines.map((ln) => {
          const mine = entities.filter((e) => e.line_number === ln.line_number)
          return (
            <div key={ln.line_number} className="flex gap-4">
              <span className="w-10 shrink-0 select-none text-right text-zinc-600">{ln.line_number}</span>
              <span className="whitespace-pre-wrap break-all">
                {segments(ln.text, mine).map((s, i) => {
                  if (!s.e) return <span key={i}>{s.t}</span>
                  const e = s.e
                  if (xray) {
                    const hidden = filter !== 'ALL' && e.category !== filter
                    if (hidden) return <span key={i}>{s.t}</span>
                    return (
                      <button
                        key={i}
                        type="button"
                        onClick={() => onToggle(e.id)}
                        title={`${e.entity_type} • ${Math.round((e.score || 0) * 100)}%`}
                        className={`rounded px-0.5 ${CATEGORIES[e.category].mark} ${e.selected_for_redaction ? '' : 'opacity-40'}`}
                      >
                        {s.t}
                      </button>
                    )
                  }
                  if (!e.selected_for_redaction) return <span key={i}>{s.t}</span>
                  return (
                    <button
                      key={i}
                      type="button"
                      onClick={() => onToggle(e.id)}
                      className="bar-in rounded-sm bg-zinc-900 px-0.5 text-zinc-100"
                    >
                      {textReplacement(s.t, e.entity_type, mode)}
                    </button>
                  )
                })}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
