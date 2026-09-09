// frontend/src/components/jobs/JobList.jsx
import { useState } from 'react'
import Spinner from '../ui/Spinner'
import { formatEnumLabel } from '../../utils/format'

const STATUS_STYLES = {
  draft: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  published: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  closed: 'bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-500',
}

const TOGGLE_BUTTON_CLASSES = (active) =>
  `shrink-0 rounded border px-3 py-1.5 text-xs font-medium ${
    active
      ? 'border-slate-400 bg-slate-100 text-slate-800 dark:border-slate-500 dark:bg-slate-700 dark:text-slate-100'
      : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
  }`

function JobRow({ job, onOpenDetails, isApplicant, myApplication, onApply, onWithdraw, applying }) {
  const [expanded, setExpanded] = useState(null) // 'description' | 'jd' | null

  const toggle = (section) => (e) => {
    e.stopPropagation()
    setExpanded((cur) => (cur === section ? null : section))
  }

  const subline = [job.location, formatEnumLabel(job.employment_type), formatEnumLabel(job.remote_type)]
    .filter(Boolean)
    .join(' · ')

  return (
    <div className="border-b border-slate-100 last:border-0 dark:border-slate-800">
      <div className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/50">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-medium text-slate-900 dark:text-slate-100">{job.title}</span>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[job.status]}`}>
              {formatEnumLabel(job.status)}
            </span>
          </div>
          {subline && (
            <div className="mt-0.5 truncate text-xs text-slate-400 dark:text-slate-500">{subline}</div>
          )}
        </div>

        <button onClick={toggle('description')} className={TOGGLE_BUTTON_CLASSES(expanded === 'description')}>
          Description
        </button>

        <button onClick={toggle('jd')} className={TOGGLE_BUTTON_CLASSES(expanded === 'jd')}>
          JD
        </button>

        <button
          onClick={() => onOpenDetails(job)}
          className={TOGGLE_BUTTON_CLASSES(false)}
        >
          Metadata
        </button>

        {isApplicant && job.status === 'published' && (
          myApplication ? (
            <button
              onClick={() => onWithdraw(myApplication)}
              disabled={applying}
              className="shrink-0 rounded px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:text-red-400 dark:hover:bg-red-950"
            >
              {applying ? 'Withdrawing…' : 'Withdraw'}
            </button>
          ) : (
            <button
              onClick={() => onApply(job)}
              disabled={applying}
              className="shrink-0 rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600"
            >
              {applying ? 'Applying…' : 'Apply'}
            </button>
          )
        )}
      </div>

      {expanded === 'description' && (
        <div className="border-t border-slate-100 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-800/40 dark:text-slate-300">
          {job.description || 'No description provided.'}
        </div>
      )}

      {expanded === 'jd' && (
        <div className="border-t border-slate-100 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-800/40 dark:text-slate-300">
          {job.jd_raw_text ? (
            <p className="max-h-48 overflow-y-auto whitespace-pre-wrap">{job.jd_raw_text}</p>
          ) : (
            'No job description file uploaded yet.'
          )}
        </div>
      )}
    </div>
  )
}

export default function JobList({
  jobs, loading, error, onRetry, onSelectJob,
  isApplicant, myApplicationsByJob = {}, onApply, onWithdraw, applyingJobId,
}) {
  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" label="Loading jobs" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-8 text-center dark:border-red-900 dark:bg-red-950">
        <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        <button onClick={onRetry} className="mt-3 text-sm font-medium text-red-800 underline hover:no-underline dark:text-red-300">
          Try again
        </button>
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 px-6 py-16 text-center dark:border-slate-700">
        <p className="text-sm text-slate-500 dark:text-slate-400">No jobs to show yet.</p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      {jobs.map((job) => (
        <JobRow
          key={job.id}
          job={job}
          onOpenDetails={onSelectJob}
          isApplicant={isApplicant}
          myApplication={myApplicationsByJob[job.id]}
          onApply={onApply}
          onWithdraw={onWithdraw}
          applying={applyingJobId === job.id}
        />
      ))}
    </div>
  )
}