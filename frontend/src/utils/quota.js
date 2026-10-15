import { formatEnumLabel } from './format'

// The backend reports its rate-limiter state as a loose object, e.g.
//   { backend: 'redis', window_seconds: 60, tokens_in_window: 0, requests_in_window: 0 }
// This turns it into one predictable shape so the UI never has to guess key
// names (and never has to JSON.stringify anything into the page).
//
// Each metric accepts several alias keys; the first one present wins. Limits
// are optional -- if the server doesn't send one, we don't invent one.
const KEYS = {
  backend: ['backend'],
  window: ['window_seconds', 'window'],
  tokensUsed: ['tokens_in_window', 'tokens_used', 'tokens'],
  tokensLimit: ['tokens_limit', 'token_limit', 'max_tokens', 'tokens_per_window', 'tokens_max'],
  requestsUsed: ['requests_in_window', 'requests_used', 'requests', 'used', 'current'],
  requestsLimit: ['requests_limit', 'request_limit', 'max_requests', 'requests_per_window', 'requests_max', 'limit'],
}
const CONSUMED = new Set(Object.values(KEYS).flat())

function pick(obj, keys) {
  for (const key of keys) if (obj[key] !== undefined && obj[key] !== null) return obj[key]
  return undefined
}

function toNumber(value) {
  if (value === undefined || value === null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

// 60 -> "last minute", 300 -> "last 5 minutes", 45 -> "last 45 seconds"
export function describeWindow(seconds) {
  if (!seconds || seconds <= 0) return 'current window'
  if (seconds === 60) return 'last minute'
  if (seconds === 3600) return 'last hour'
  if (seconds % 3600 === 0) return `last ${seconds / 3600} hours`
  if (seconds > 60 && seconds % 60 === 0) return `last ${seconds / 60} minutes`
  return `last ${seconds} seconds`
}

function formatExtra(value) {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

// Returns null when the payload isn't an object we can read (caller shows a fallback).
export function normalizeQuota(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null

  const windowSeconds = toNumber(pick(raw, KEYS.window))
  const backend = pick(raw, KEYS.backend)

  // Anything we don't recognise but can safely print (string/number/boolean)
  // is kept, so a new backend field shows up without a frontend change.
  const extras = Object.entries(raw)
    .filter(([key, value]) => !CONSUMED.has(key) && ['string', 'number', 'boolean'].includes(typeof value))
    .slice(0, 6)
    .map(([key, value]) => ({ label: formatEnumLabel(key), value: formatExtra(value) }))

  return {
    backend: backend ? String(backend) : null,
    windowSeconds,
    windowLabel: describeWindow(windowSeconds),
    tokens: { used: toNumber(pick(raw, KEYS.tokensUsed)), limit: toNumber(pick(raw, KEYS.tokensLimit)) },
    requests: { used: toNumber(pick(raw, KEYS.requestsUsed)), limit: toNumber(pick(raw, KEYS.requestsLimit)) },
    extras,
  }
}
