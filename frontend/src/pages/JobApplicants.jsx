import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { fetchJob } from '../api/jobs'
import ApplicantsPanel from '../components/jobs/ApplicantsPanel'
import Spinner from '../components/ui/Spinner'
import { formatEnumLabel, getErrorMessage } from '../utils/format'

const STATUS_STYLES = {
  draft: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  published: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  closed: 'bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-500',
}

// Dedicated page (meant to be opened via window.open in a new tab, not
// rendered inline) so a recruiter — or a future matching model reading this
// same route — has the JD and every applicant's resume link on one screen,
// instead of a cramped modal with a scrollable table.
export default function JobApplicants() {
  const { jobId } = useParams()
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

      <div className="mb-6 rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">Job description</h2>
        {job.jd_raw_text ? (
          <p className="whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">{job.jd_raw_text}</p>
        ) : (
          <p className="text-sm text-slate-400 dark:text-slate-500">No job description file uploaded yet.</p>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">Applicants</h2>
        <ApplicantsPanel job={job} active fullPage />
      </div>
    </div>
  )
}