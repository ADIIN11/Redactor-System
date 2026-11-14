export const BANNER =
  '========================================================\n' +
  '[DECLASSIFIED CLONE // SENSITIVE PII REDACTED // CB-02]\n' +
  '========================================================'

// Mirrors backend/engine/redactor.py so the live preview matches the export
export function textReplacement(text, type, mode) {
  if (mode === 'cia_blackout') return '█'.repeat(text.length)
  if (mode === 'partial_mask') {
    if (type === 'IN_AADHAAR') return '[Aadhaar Redacted]'
    const n = text.length
    if (n <= 2) return '*'.repeat(n)
    const keep = n === 3 ? 1 : Math.min(4, Math.max(2, Math.round(n * 0.3)))
    return '*'.repeat(n - keep) + text.slice(n - keep)
  }
  return `[REDACTED:${type}]`
}

export function riskLevel(entities) {
  if (entities.length === 0) return 'CLEAN'
  const severe = entities.some((e) => e.category === 'GOV_ID' || e.category === 'FINANCIAL')
  return severe ? 'CRITICAL' : 'MODERATE'
}

const D = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
  [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
  [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
  [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
  [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
  [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
  [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
  [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
  [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
const P = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
  [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
  [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
  [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
  [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
  [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
  [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

function verhoeff(digits) {
  let c = 0
  digits
    .split('')
    .reverse()
    .forEach((ch, i) => {
      c = D[c][P[i % 8][Number(ch)]]
    })
  return c === 0
}

function luhn(digits) {
  let sum = 0
  digits
    .split('')
    .reverse()
    .forEach((ch, i) => {
      let n = Number(ch)
      if (i % 2 === 1) {
        n *= 2
        if (n > 9) n -= 9
      }
      sum += n
    })
  return sum % 10 === 0
}

// Client-side checksum label shown as the green verification pill
export function verificationLabel(e) {
  const digits = (e.text || '').replace(/\D/g, '')
  if (e.entity_type === 'IN_AADHAAR' && digits.length === 12 && verhoeff(digits)) {
    return '✓ Verhoeff Verified'
  }
  if (/CARD/.test(e.entity_type) && digits.length >= 13 && digits.length <= 19 && luhn(digits)) {
    return '✓ Luhn Verified'
  }
  if (e.entity_type === 'IN_PAN' && /^[A-Z]{5}[0-9]{4}[A-Z]$/.test(e.text)) {
    return '✓ PAN Format Verified'
  }
  return null
}
