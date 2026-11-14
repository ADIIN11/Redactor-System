import { Download, ShieldCheck, X } from 'lucide-react'
import { CATEGORIES, categoryOf } from '../lib/theme'
import { downloadJson } from '../lib/api'

export default function AuditCertificateModal({ receipt, onClose }) {
  const cert = receipt.certificate
  const byCategory = {}
  Object.entries(receipt.entity_counts).forEach(([type, n]) => {
    const cat = categoryOf(type)
    byCategory[cat] = (byCategory[cat] || 0) + n
  })
  const flattened = cert.zero_leak && cert.zero_leak.flattened_raster_only

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-xl rounded-xl border border-zinc-700 bg-zinc-900 p-6" onClick={(ev) => ev.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><ShieldCheck className="text-emerald-400" /> Redaction Audit Certificate</h2>
          <button onClick={onClose}><X size={18} /></button>
        </div>
        <dl className="space-y-3 font-mono text-xs">
          <div><dt className="text-zinc-500">SHA-256 · ORIGINAL</dt><dd className="break-all">{receipt.sha256_original}</dd></div>
          <div><dt className="text-zinc-500">SHA-256 · REDACTED CLONE</dt><dd className="break-all text-emerald-400">{receipt.sha256_redacted}</dd></div>
        </dl>
        <div className="mt-4 flex flex-wrap gap-2">
          {Object.entries(byCategory).map(([cat, n]) => (
            <span key={cat} className={`rounded border px-2 py-1 font-mono text-xs ${CATEGORIES[cat].badge}`}>{CATEGORIES[cat].label}: {n}</span>
          ))}
          <span className="rounded border border-zinc-600 px-2 py-1 font-mono text-xs">Total scrubbed: {receipt.total_redacted}</span>
        </div>
        <p className="mt-4 rounded border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-300">
          {flattened
            ? 'Zero-Leak Stream Flattening confirmed: every page was rasterized and rebuilt. No original text stream, fonts or metadata were carried into the clone.'
            : 'Text-stream replacement confirmed: redacted spans were overwritten in the clone and the original text is not retained.'}
        </p>
        <button
          onClick={() => downloadJson(cert, receipt.output_filename.replace(/\.[^.]+$/, '') + '_AUDIT_RECEIPT.json')}
          className="mt-4 flex items-center gap-2 rounded-lg bg-zinc-100 px-4 py-2 text-sm font-semibold text-zinc-900 hover:bg-white"
        >
          <Download size={16} /> Download JSON Audit Receipt
        </button>
      </div>
    </div>
  )
}
