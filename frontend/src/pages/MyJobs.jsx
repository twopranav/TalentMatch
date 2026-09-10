import { useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useJobs } from '../hooks/useJobs'
import { updateJob } from '../api/jobs'
import JobFormDrawer from '../components/jobs/JobFormDrawer'
import Spinner from '../components/ui/Spinner'
import { useToast } from '../components/ui/Toast'
import { formatEnumLabel, getErrorMessage } from '../utils/format'

const STATUS_STYLES = {
  draft: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  published: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  closed: 'bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-500',
}

export default function MyJobs() {
  const { user } = useAuth()
  // No status filter — list_jobs already returns every status (not just
  // published) to any non-USER role, so recruiters see their own drafts too.
  const { jobs, loading, error, refetch } = useJobs({})
  const { showToast } = useToast()

  const myJobs = useMemo(
    () => jobs.filter((j) => j.created_by_id === user?.id),
    [jobs, user],
  )

  const [editingJob, setEditingJob] = useState(null)
  const [formOpen, setFormOpen] = useState(false)
  const [busyJobId, setBusyJobId] = useState(null)

  const openEdit = (job) => {
    setEditingJob(job)
    setFormOpen(true)
  }

  // Opens the dedicated applicants page in a new tab/window instead of a
  // small modal, so the JD and every resume link are visible on one screen.
  const openApplicants = (job) => {
    window.open(`/jobs/${job.id}/applicants`, '_blank', 'noopener,noreferrer')
  }

  const setStatus = async (job, status) => {
    setBusyJobId(job.id)
    try {
      await updateJob(job.id, { status })
      showToast(`Job marked ${formatEnumLabel(status).toLowerCase()}.`, 'success')
      refetch()
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not update the job status.'), 'error')
    } finally {
      setBusyJobId(null)
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="mb-6 text-xl font-semibold text-slate-900 dark:text-slate-100">My Jobs</h1>

      {loading && (
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading jobs" />
        </div>
      )}

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {!loading && !error && myJobs.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 px-6 py-16 text-center dark:border-slate-700">
          <p className="text-sm text-slate-500 dark:text-slate-400">You haven't posted any jobs yet.</p>
        </div>
      )}

      {!loading && !error && myJobs.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          {myJobs.map((job) => (
            <div
              key={job.id}
              className="flex flex-wrap items-center gap-3 border-b border-slate-100 px-4 py-3 last:border-0 dark:border-slate-800"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium text-slate-900 dark:text-slate-100">{job.title}</span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[job.status]}`}>
                    {formatEnumLabel(job.status)}
                  </span>
                </div>
                <div className="mt-0.5 truncate text-xs text-slate-400 dark:text-slate-500">
                  {[job.location, formatEnumLabel(job.employment_type), formatEnumLabel(job.remote_type)]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-2">
                {job.status === 'draft' && (
                  <button
                    onClick={() => setStatus(job, 'published')}
                    disabled={busyJobId === job.id}
                    className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
                  >
                    Publish
                  </button>
                )}
                {job.status === 'published' && (
                  <button
                    onClick={() => setStatus(job, 'closed')}
                    disabled={busyJobId === job.id}
                    className="rounded bg-slate-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-60"
                  >
                    Close
                  </button>
                )}
                <button
                  onClick={() => openEdit(job)}
                  className="rounded border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  Edit
                </button>
                <button
                  onClick={() => openApplicants(job)}
                  className="rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600"
                >
                  Applicants
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <JobFormDrawer open={formOpen} onClose={() => setFormOpen(false)} job={editingJob} onSaved={refetch} />
    </div>
  )
}