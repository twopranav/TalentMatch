import { useState } from 'react'
import { useMyApplications } from '../hooks/useApplications'
import { fetchJob } from '../api/jobs'
import JobDetailsModal from '../components/jobs/JobDetailsModal'
import Spinner from '../components/ui/Spinner'
import { useToast } from '../components/ui/Toast'
import { formatEnumLabel } from '../utils/format'

const APPLICATION_STATUS_STYLES = {
  applied: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  under_review: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  shortlisted: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  rejected: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  hired: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
}

export default function AppliedJobs() {
  const { applications, loading, error, refetch } = useMyApplications()
  const { showToast } = useToast()
  const [selectedJob, setSelectedJob] = useState(null)
  const [selectedApplication, setSelectedApplication] = useState(null)
  const [openingId, setOpeningId] = useState(null)

  const openJob = async (application) => {
    setOpeningId(application.id)
    try {
      const job = await fetchJob(application.job_id)
      setSelectedJob(job)
      setSelectedApplication(application)
    } catch (err) {
      showToast('Could not load this job.', 'error')
    } finally {
      setOpeningId(null)
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="mb-6 text-xl font-semibold text-slate-900 dark:text-slate-100">Applied Jobs</h1>

      {loading && (
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading applications" />
        </div>
      )}

      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {!loading && !error && applications.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 px-6 py-16 text-center dark:border-slate-700">
          <p className="text-sm text-slate-500 dark:text-slate-400">You haven't applied to any jobs yet.</p>
        </div>
      )}

      {!loading && !error && applications.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          {applications.map((app) => (
            <button
              key={app.id}
              onClick={() => openJob(app)}
              disabled={openingId === app.id}
              className="flex w-full items-center gap-3 border-b border-slate-100 px-4 py-3 text-left last:border-0 hover:bg-slate-50 disabled:opacity-60 dark:border-slate-800 dark:hover:bg-slate-800/50"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium text-slate-900 dark:text-slate-100">{app.job_title}</span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${APPLICATION_STATUS_STYLES[app.status]}`}>
                    {formatEnumLabel(app.status)}
                  </span>
                </div>
                <div className="mt-0.5 truncate text-xs text-slate-400 dark:text-slate-500">
                  {[app.company, app.location].filter(Boolean).join(' · ') || '—'}
                </div>
              </div>
              <div className="shrink-0 text-xs text-slate-400 dark:text-slate-500">
                Applied {new Date(app.applied_at).toLocaleDateString()}
              </div>
            </button>
          ))}
        </div>
      )}

      <JobDetailsModal
        open={Boolean(selectedJob)}
        onClose={() => { setSelectedJob(null); setSelectedApplication(null) }}
        job={selectedJob}
        onEdit={() => {}}
        onUploadJD={() => {}}
        onChanged={() => {}}
        onDeleted={() => {}}
        myApplication={selectedApplication}
        onApplicationChanged={refetch}
      />
    </div>
  )
}