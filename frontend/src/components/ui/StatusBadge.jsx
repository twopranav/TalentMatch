const TONES = {
  success: 'bg-emerald-100 text-emerald-800 ring-emerald-200 dark:bg-emerald-900/35 dark:text-emerald-300 dark:ring-emerald-800/70',
  warning: 'bg-amber-100 text-amber-900 ring-amber-200 dark:bg-amber-900/35 dark:text-amber-300 dark:ring-amber-800/70',
  danger: 'bg-red-100 text-red-800 ring-red-200 dark:bg-red-900/35 dark:text-red-300 dark:ring-red-800/70',
  info: 'bg-indigo-100 text-indigo-800 ring-indigo-200 dark:bg-indigo-900/35 dark:text-indigo-300 dark:ring-indigo-800/70',
  muted: 'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700',
  purple: 'bg-violet-100 text-violet-800 ring-violet-200 dark:bg-violet-900/35 dark:text-violet-300 dark:ring-violet-800/70',
}

const STATUS_TONE = {
  active: 'success', approved: 'success', completed: 'success', published: 'success', uploaded: 'success', done: 'success', hired: 'success', success: 'success', passed: 'success', ok: 'success',
  pending: 'warning', processing: 'warning', draft: 'warning', requested: 'warning', under_review: 'warning', reviewing: 'warning', interview_scheduled: 'warning', interviewing: 'warning', shortlisted: 'info', recruiter: 'warning',
  rejected: 'danger', failed: 'danger', delete: 'danger', inactive: 'muted', closed: 'muted', archived: 'muted', applied: 'muted', create: 'success', update: 'info',
  superuser: 'purple', admin: 'info', user: 'muted', unset: 'danger', missing: 'danger', disabled: 'muted', unknown: 'muted',
}

const LABELS = {
  under_review: 'Reviewing', interview_scheduled: 'Interview scheduled', interviewing: 'Interviewing', create: 'Created', update: 'Updated', delete: 'Deleted',
  active: 'Active', inactive: 'Inactive', unset: 'Not set', user: 'Applicant', admin: 'Administrator',
}

export default function StatusBadge({ status, children, tone, size = 'sm', className = '' }) {
  const key = String(status ?? 'unknown').toLowerCase().replaceAll(' ', '_')
  const resolvedTone = tone ?? STATUS_TONE[key] ?? 'muted'
  const sizeClass = size === 'md' ? 'px-2.5 py-1 text-xs' : 'px-2 py-0.5 text-[11px]'
  const label = children ?? LABELS[key] ?? String(status ?? 'Unknown').replaceAll('_', ' ')
  return <span className={`inline-flex max-w-full items-center rounded-full font-semibold capitalize leading-5 ring-1 ring-inset ${sizeClass} ${TONES[resolvedTone] ?? TONES.muted} ${className}`}>{label}</span>
}
