// frontend/src/components/jobs/JobCard.jsx
const STATUS_STYLES = {
  draft: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  published: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  closed: 'bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-500',
}

function formatLabel(value) {
  if (!value) return null
  return String(value).replace(/_/g, ' ')
}

export default function JobCard({ job, onClick }) {
  return (
    <button
      onClick={() => onClick?.(job)}
      className="w-full rounded-lg border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-slate-300 hover:shadow dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">{job.title}</h3>
        <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[job.status]}`}>
          {job.status}
        </span>
      </div>

      {job.description && (
        <p className="mt-2 line-clamp-2 text-sm text-slate-600 dark:text-slate-400">{job.description}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5 text-xs text-slate-500 dark:text-slate-400">
        {job.location && <span className="rounded bg-slate-50 px-2 py-0.5 dark:bg-slate-800">{job.location}</span>}
        {formatLabel(job.employment_type) && (
          <span className="rounded bg-slate-50 px-2 py-0.5 capitalize dark:bg-slate-800">{formatLabel(job.employment_type)}</span>
        )}
        {job.remote_type && <span className="rounded bg-slate-50 px-2 py-0.5 capitalize dark:bg-slate-800">{job.remote_type}</span>}
      </div>

      <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
        Updated {new Date(job.updated_at).toLocaleDateString()}
      </p>
    </button>
  )
}