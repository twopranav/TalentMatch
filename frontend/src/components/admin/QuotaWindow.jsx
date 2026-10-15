import { formatEnumLabel } from '../../utils/format'

// Colour tells the admin how close a limit is. It only applies when the
// server actually reports a limit; without one the gauge stays neutral.
const FILL = {
  ok: 'bg-indigo-600 dark:bg-indigo-400',
  warn: 'bg-gold-500 dark:bg-gold-400',
  critical: 'bg-red-500 dark:bg-red-400',
}

function levelFor(ratio) {
  if (ratio >= 0.9) return 'critical'
  if (ratio >= 0.7) return 'warn'
  return 'ok'
}

function Gauge({ label, unit, used, limit, windowLabel }) {
  const hasUsed = used != null
  const hasLimit = limit != null && limit > 0
  const ratio = hasLimit && hasUsed ? Math.min(1, used / limit) : 0
  const level = levelFor(ratio)

  let caption
  if (!hasUsed) caption = 'Not reported'
  else if (hasLimit && used > limit) caption = `Over the limit by ${(used - limit).toLocaleString()} ${unit}`
  else if (hasLimit) caption = `${(limit - used).toLocaleString()} ${unit} left in the ${windowLabel}`
  else if (used === 0) caption = `None used in the ${windowLabel}`
  else caption = `${unit} in the ${windowLabel}, no limit reported`

  return <div>
    <div className="flex items-baseline justify-between gap-3">
      <p className="text-sm font-medium text-slate-600 dark:text-slate-300">{label}</p>
      {hasLimit && hasUsed && <p className="text-xs tabular-nums text-slate-500 dark:text-slate-400">{Math.round(ratio * 100)}% used</p>}
    </div>
    <p className="mt-1 font-display text-4xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">
      {hasUsed ? used.toLocaleString() : '—'}
      {hasLimit && <span className="ml-2 font-sans text-sm font-normal text-slate-500 dark:text-slate-400">of {limit.toLocaleString()}</span>}
    </p>
    <div
      {...(hasLimit && hasUsed ? { role: 'meter', 'aria-label': `${label} used`, 'aria-valuemin': 0, 'aria-valuemax': limit, 'aria-valuenow': Math.min(used, limit) } : { 'aria-hidden': true })}
      className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"
    >
      <div className={`h-full rounded-full transition-[width] duration-500 ${FILL[level]}`} style={{ width: `${ratio * 100}%` }} />
    </div>
    <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{caption}</p>
  </div>
}

// Where the counters live. Redis is shared by every server; anything else
// (an in-process fallback) means each server counts on its own, which is
// worth flagging because limits then apply per server, not overall.
function BackendChip({ backend }) {
  if (!backend) return null
  const shared = backend.toLowerCase() === 'redis'
  return <span className={`inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${shared ? 'bg-emerald-50 text-emerald-800 ring-emerald-700/15 dark:bg-emerald-950/60 dark:text-emerald-300' : 'bg-amber-50 text-amber-800 ring-amber-700/15 dark:bg-amber-950/50 dark:text-amber-300'}`}>
    <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${shared ? 'bg-emerald-500' : 'bg-amber-500'}`} />
    {formatEnumLabel(backend)}{shared ? '' : ', not shared across servers'}
  </span>
}

export default function QuotaWindow({ quota }) {
  if (!quota) return null
  return <div>
    <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-2">
      <BackendChip backend={quota.backend} />
      <span className="text-sm text-slate-500 dark:text-slate-400">Counting usage over the {quota.windowLabel}</span>
    </div>
    <div className="grid grid-cols-2 gap-10">
      <Gauge label="LLM tokens" unit="tokens" used={quota.tokens.used} limit={quota.tokens.limit} windowLabel={quota.windowLabel} />
      <Gauge label="Requests" unit="requests" used={quota.requests.used} limit={quota.requests.limit} windowLabel={quota.windowLabel} />
    </div>
    {quota.extras.length > 0 && <dl className="mt-6 flex flex-wrap gap-x-8 gap-y-2 border-t border-slate-100 pt-4 text-xs dark:border-slate-800">
      {quota.extras.map((item) => <div key={item.label} className="flex gap-2"><dt className="text-slate-500 dark:text-slate-400">{item.label}</dt><dd className="font-medium tabular-nums text-slate-800 dark:text-slate-200">{item.value}</dd></div>)}
    </dl>}
  </div>
}
