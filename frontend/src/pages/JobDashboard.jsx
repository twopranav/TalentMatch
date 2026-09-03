import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useJobs } from '../hooks/useJobs'
import JobList from '../components/jobs/JobList'

const STATUS_OPTIONS = ['all', 'draft', 'published', 'closed']

export default function JobDashboard() {
  const { user } = useAuth()
  const [statusFilter, setStatusFilter] = useState('all')

  // "all" means no status param — USER role still gets server-side
  // restricted to published only, per the fixed list_jobs logic
  const { jobs, loading, error, refetch } = useJobs(
    statusFilter === 'all' ? undefined : statusFilter
  )

  const canFilterByStatus = user?.role !== 'user'

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Job Dashboard</h1>

        {canFilterByStatus && (
          <div className="flex gap-2">
            {STATUS_OPTIONS.map((option) => (
              <button
                key={option}
                onClick={() => setStatusFilter(option)}
                className={`rounded px-3 py-1.5 text-sm font-medium capitalize ${
                  statusFilter === option
                    ? 'bg-slate-800 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        )}
      </div>

      <JobList jobs={jobs} loading={loading} error={error} onRetry={refetch} />
    </div>
  )
}