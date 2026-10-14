const styles = {
  success: 'bg-emerald-50 text-emerald-800 ring-emerald-700/15 dark:bg-emerald-950/60 dark:text-emerald-300',
  warning: 'bg-amber-50 text-amber-800 ring-amber-700/15 dark:bg-amber-950/50 dark:text-amber-300',
  danger: 'bg-red-50 text-red-800 ring-red-700/15 dark:bg-red-950/50 dark:text-red-300',
  info: 'bg-indigo-50 text-indigo-800 ring-indigo-700/15 dark:bg-indigo-950/60 dark:text-indigo-300',
  neutral: 'bg-slate-100 text-slate-700 ring-slate-600/15 dark:bg-slate-800 dark:text-slate-300',
}

export function statusTone(status) {
  const value = String(status ?? '').toLowerCase()
  if (['uploaded', 'success', 'complete', 'completed', 'hired', 'published', 'approved'].includes(value)) return 'success'
  if (['pending', 'processing', 'under_review', 'review', 'draft', 'requested'].includes(value)) return 'warning'
  if (['failed', 'rejected', 'closed', 'error', 'not_proceeding'].includes(value)) return 'danger'
  if (['shortlisted', 'interview_scheduled', 'queued'].includes(value)) return 'info'
  return 'neutral'
}

export default function StatusBadge({ status, tone, children, className = '' }) {
  const label = children ?? String(status ?? 'Unknown').replaceAll('_', ' ')
  return <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium capitalize ring-1 ring-inset ${styles[tone ?? statusTone(status)] ?? styles.neutral} ${className}`}>{label}</span>
}
