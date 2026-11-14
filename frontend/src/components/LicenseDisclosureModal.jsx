import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { fetchLicenses } from '../lib/api'

const FRONTEND = [
  { name: 'React', license: 'MIT', purpose: 'UI library' },
  { name: 'Vite', license: 'MIT', purpose: 'Build tooling' },
  { name: 'Tailwind CSS', license: 'MIT', purpose: 'Styling' },
  { name: 'Lucide React', license: 'ISC', purpose: 'Icons' },
]

export default function LicenseDisclosureModal({ onClose }) {
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    fetchLicenses().then(setRows).catch((err) => setError(err.message))
  }, [])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="max-h-[85vh] w-full max-w-3xl overflow-auto rounded-xl border border-zinc-700 bg-zinc-900 p-6" onClick={(ev) => ev.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Open-Source Component Disclosure</h2>
          <button onClick={onClose}><X size={18} /></button>
        </div>
        {error && <p className="mb-3 text-xs text-amber-400">Backend list unavailable ({error}). Showing frontend components only.</p>}
        <table className="w-full text-left text-sm">
          <thead className="text-[11px] uppercase tracking-widest text-zinc-500">
            <tr><th className="py-2">Component</th><th>Version</th><th>License</th><th>Purpose</th></tr>
          </thead>
          <tbody>
            {[...rows, ...FRONTEND].map((r) => (
              <tr key={r.name} className="border-t border-zinc-800">
                <td className="py-2 pr-2">{r.homepage ? <a className="text-cyan-400 hover:underline" href={r.homepage} target="_blank" rel="noreferrer">{r.name}</a> : r.name}</td>
                <td className="font-mono text-xs text-zinc-400">{r.version || '-'}</td>
                <td className="font-mono text-xs">{r.license}</td>
                <td className="text-zinc-400">{r.purpose}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
