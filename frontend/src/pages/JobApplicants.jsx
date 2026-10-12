import { useEffect, useState } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import { fetchJob } from '../api/jobs'
import { useAuth } from '../context/AuthContext'
import BulkApplyPanel from '../components/jobs/BulkApplyPanel'
import ApplicantsPanel from '../components/jobs/ApplicantsPanel'
import Spinner from '../components/ui/Spinner'
import { formatEnumLabel, getErrorMessage } from '../utils/format'

const STATUS_STYLES = {
  draft: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  published: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  closed: 'bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-500',
}

const TABS = [
  { key: 'all', label: 'All applicants' },
  { key: 'shortlisted', label: 'Shortlisted' },
]

// Only these roles get the bulk-apply panel (candidates and admins never see it).
const BULK_APPLY_ROLES = ['recruiter', 'superuser']

// Dedicated page (meant to be opened via window.open in a new tab, not
// rendered inline) so a recruiter — or a future matching model reading this
// same route — has the JD and every applicant's resume link on one screen,
// instead of a cramped modal with a scrollable table.
export default function JobApplicants() {
  const { jobId } = useParams()
  const { user } = useAuth()
  const [refreshKey, setRefreshKey] = useState(0)
  // The tab lives in the URL (?tab=shortlisted) so it survives a refresh and can be linked to.
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get('tab') === 'shortlisted' ? 'shortlisted' : 'all'
  const selectTab = (key) => {
    setSearchParams(key === 'all' ? {} : { tab: key }, { replace: true })
  }
  const [job, setJob] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchJob(jobId)
      .then(setJob)
      .catch((err) => setError(getErrorMessage(err, 'Could not load this job.')))
      .finally(() => setLoading(false))
  }, [jobId])

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" label="Loading job" />
      </div>
    )
  }

  if (error || !job) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <p className="text-sm text-red-600 dark:text-red-400">{error || 'Job not found.'}</p>
        <Link to="/my-jobs" className="mt-3 inline-block text-sm font-medium text-slate-700 underline hover:no-underline dark:text-slate-300">
          Back to My Jobs
        </Link>
      </div>
    )
  }

  const canBulkApply = BULK_APPLY_ROLES.includes(user?.role)

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">{job.title}</h1>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[job.status]}`}>
            {formatEnumLabel(job.status)}
          </span>
        </div>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          {[job.location, formatEnumLabel(job.employment_type), formatEnumLabel(job.remote_type)]
            .filter(Boolean)
            .join(' · ')}
        </p>
      </div>

      {canBulkApply && (
        job.status === 'published' ? (
          <BulkApplyPanel job={job} onApplied={() => setRefreshKey((k) => k + 1)} />
        ) : (
          <p className="mb-6 text-xs text-slate-500 dark:text-slate-400">
            Publish this job to add resumes from your library as applicants.
          </p>
        )
      )}

      <div className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
        <div role="tablist" aria-label="Applicant views" className="mb-4 flex gap-1 border-b border-slate-200 dark:border-slate-800">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              id={`applicants-tab-${t.key}`}
              aria-selected={tab === t.key}
              aria-controls={`applicants-panel-${t.key}`}
              onClick={() => selectTab(t.key)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${
                tab === t.key
                  ? 'border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300'
                  : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Both panels stay mounted so each keeps its own filters and page when
            you switch tabs; only the visible one fetches (active) and it
            refreshes on becoming visible, so a status change made in the other
            tab always shows up. */}
        <div role="tabpanel" id="applicants-panel-all" aria-labelledby="applicants-tab-all" hidden={tab !== 'all'}>
          <ApplicantsPanel job={job} active={tab === 'all'} fullPage refreshKey={refreshKey} />
        </div>
        <div role="tabpanel" id="applicants-panel-shortlisted" aria-labelledby="applicants-tab-shortlisted" hidden={tab !== 'shortlisted'}>
          <ApplicantsPanel job={job} mode="shortlisted" active={tab === 'shortlisted'} fullPage refreshKey={refreshKey} />
        </div>
      </div>
    </div>
  )
}