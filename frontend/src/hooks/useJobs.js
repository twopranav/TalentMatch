import { useCallback, useEffect, useState } from 'react'
import { fetchJobs } from '../api/jobs'

export function useJobs(statusFilter) {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    fetchJobs(statusFilter)
      .then(setJobs)
      .catch((err) => {
        // 403 shouldn't happen post-fix, but a stale/expired token still can
        const message =
          err.response?.status === 401
            ? 'Your session has expired. Please log in again.'
            : 'Could not load jobs. Please try again.'
        setError(message)
      })
      .finally(() => setLoading(false))
  }, [statusFilter])

  useEffect(() => {
    load()
  }, [load])

  return { jobs, loading, error, refetch: load }
}