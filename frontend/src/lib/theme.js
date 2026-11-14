// Full class strings so Tailwind can detect them statically
export const CATEGORIES = {
  GOV_ID: {
    label: 'Gov IDs',
    box: 'border-rose-500 bg-rose-500/20',
    pill: 'bg-rose-500 text-white',
    badge: 'border-rose-500/50 bg-rose-500/10 text-rose-400',
    mark: 'bg-rose-500/20 text-rose-300 ring-1 ring-rose-500/60',
  },
  FINANCIAL: {
    label: 'Financial',
    box: 'border-amber-500 bg-amber-500/20',
    pill: 'bg-amber-500 text-zinc-950',
    badge: 'border-amber-500/50 bg-amber-500/10 text-amber-400',
    mark: 'bg-amber-500/20 text-amber-300 ring-1 ring-amber-500/60',
  },
  CONTACT_PII: {
    label: 'Contact PII',
    box: 'border-cyan-400 bg-cyan-400/20',
    pill: 'bg-cyan-400 text-zinc-950',
    badge: 'border-cyan-400/50 bg-cyan-400/10 text-cyan-300',
    mark: 'bg-cyan-400/20 text-cyan-200 ring-1 ring-cyan-400/60',
  },
  CUSTOM_BOX: {
    label: 'Custom',
    box: 'border-emerald-500 bg-emerald-500/20',
    pill: 'bg-emerald-500 text-zinc-950',
    badge: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400',
    mark: 'bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/60',
  },
}

export function categoryOf(type = '') {
  if (type === 'CUSTOM_BOX') return 'CUSTOM_BOX'
  if (/AADHAAR|PAN|PASSPORT|VOTER|DRIVING|SSN/.test(type)) return 'GOV_ID'
  if (/CARD|BANK|IFSC|ACCOUNT|UPI|IBAN/.test(type)) return 'FINANCIAL'
  return 'CONTACT_PII'
}

export const MODES = [
  {
    id: 'cia_blackout',
    title: 'CIA Classified Blackout',
    desc: 'Solid #000000 bars + zero-leak raster flattening',
  },
  {
    id: 'partial_mask',
    title: 'Smart Partial Mask',
    desc: 'Preserves trailing 4 chars for verification (strict full redaction for national IDs)',
  },
  {
    id: 'entity_tag',
    title: 'Semantic Entity Tag',
    desc: 'Replaces span with [REDACTED: ENTITY_TYPE]',
  },
]
