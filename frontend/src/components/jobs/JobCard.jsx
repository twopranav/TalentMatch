const STATUS_STYLES = {
  draft: 'bg-slate-100 text-slate-700',
  published: 'bg-emerald-100 text-emerald-800',
  closed: 'bg-slate-200 text-slate-500',
}

export default function JobCard({ job }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-base font-semibold text-slate-900">{job.title}</h3>
        <span
          className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[job.status]}`}
        >
          {job.status}
        </span>
      </div>
      {job.description && (
        <p className="mt-2 line-clamp-2 text-sm text-slate-600">{job.description}</p>
      )}
      <p className="mt-3 text-xs text-slate-400">
        Updated {new Date(job.updated_at).toLocaleDateString()}
      </p>
    </div>
  )
}