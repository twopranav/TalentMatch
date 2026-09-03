import Spinner from '../ui/Spinner'
import JobCard from './JobCard'

export default function JobList({ jobs, loading, error, onRetry }) {
  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" label="Loading jobs" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-8 text-center">
        <p className="text-sm text-red-700">{error}</p>
        <button
          onClick={onRetry}
          className="mt-3 text-sm font-medium text-red-800 underline hover:no-underline"
        >
          Try again
        </button>
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 px-6 py-16 text-center">
        <p className="text-sm text-slate-500">No jobs to show yet.</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {jobs.map((job) => (
        <JobCard key={job.id} job={job} />
      ))}
    </div>
  )
}