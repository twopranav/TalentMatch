// frontend/src/pages/JobDashboard.jsx
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useJobs } from '../hooks/useJobs'
import JobList from '../components/jobs/JobList'
import JobFilterBar from '../components/jobs/JobFilterBar'
import JobFormDrawer from '../components/jobs/JobFormDrawer'
import JDUploadModal from '../components/jobs/JDUploadModal'
import JobDetailsModal from '../components/jobs/JobDetailsModal'

const STATUS_OPTIONS = ['all', 'draft', 'published', 'closed']

export default function JobDashboard() {
  const { user } = useAuth()
  const [filters, setFilters] = useState({
    status: 'all',
    location: '',
    department: '',
    employment_type: '',
    seniority: '',
    remote_type: '',
  })

  const canManageJobs = user?.role === 'recruiter' || user?.role === 'admin' || user?.role === 'superuser'
  const canFilterByStatus = user?.role !== 'user'

  const { jobs, loading, error, refetch } = useJobs({
    ...filters,
    status: filters.status === 'all' ? undefined : filters.status,
  })

  const [selectedJob, setSelectedJob] = useState(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editingJob, setEditingJob] = useState(null)
  const [uploadJob, setUploadJob] = useState(null)

  const openCreate = () => {
    setEditingJob(null)
    setFormOpen(true)
  }

  const openEdit = (job) => {
    setSelectedJob(null)
    setEditingJob(job)
    setFormOpen(true)
  }

  const handleChanged = (updated) => {
    setSelectedJob(updated)
    refetch()
  }

  const handleUploaded = (updated) => {
    setSelectedJob(updated)
    refetch()
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Job Dashboard</h1>

        <div className="flex flex-wrap items-center gap-3">
          {canFilterByStatus && (
            <div className="flex flex-wrap gap-2">
              {STATUS_OPTIONS.map((option) => (
                <button
                  key={option}
                  onClick={() => setFilters((f) => ({ ...f, status: option }))}
                  className={`rounded px-3 py-1.5 text-sm font-medium capitalize ${
                    filters.status === option
                      ? 'bg-slate-800 text-white dark:bg-slate-700'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          )}

          {canManageJobs && (
            <button onClick={openCreate} className="rounded bg-slate-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600">
              + New job
            </button>
          )}
        </div>
      </div>

      <JobFilterBar filters={filters} onChange={setFilters} />

      <JobList jobs={jobs} loading={loading} error={error} onRetry={refetch} onSelectJob={setSelectedJob} />

      <JobDetailsModal
        open={Boolean(selectedJob)}
        onClose={() => setSelectedJob(null)}
        job={selectedJob}
        onEdit={openEdit}
        onUploadJD={(job) => { setSelectedJob(null); setUploadJob(job) }}
        onChanged={handleChanged}
        onDeleted={refetch}
      />

      <JobFormDrawer open={formOpen} onClose={() => setFormOpen(false)} job={editingJob} onSaved={refetch} />

      <JDUploadModal open={Boolean(uploadJob)} onClose={() => setUploadJob(null)} job={uploadJob} onUploaded={handleUploaded} />
    </div>
  )
}