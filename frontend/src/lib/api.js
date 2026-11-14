const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function handle(res) {
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch (err) {}
    throw new Error(msg)
  }
  return res.json()
}

export async function analyzeFile(file) {
  const form = new FormData()
  form.append('file', file)
  return handle(await fetch(`${BASE}/api/v1/analyze`, { method: 'POST', body: form }))
}

export async function cloneRedact(payload) {
  return handle(
    await fetch(`${BASE}/api/v1/clone-redact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  )
}

export async function fetchLicenses() {
  return handle(await fetch(`${BASE}/api/v1/licenses`))
}

export function base64ToBlob(b64, mime) {
  const bin = atob(b64)
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0))
  return new Blob([bytes], { type: mime })
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadJson(obj, filename) {
  saveBlob(new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' }), filename)
}
