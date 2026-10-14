import { useCallback, useEffect, useState } from 'react'
import { fetchJobsPage } from '../api/jobs'

export function useJobs(filters = {}) {
  const [jobs, setJobs] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const filtersKey = JSON.stringify(filters)

  const load = useCallback(() => {
    setLoading(true); setError(null)
    fetchJobsPage(JSON.parse(filtersKey))
      .then(({ items, total: count }) => { setJobs(items); setTotal(count) })
      .catch(() => { setError('Could not load jobs. Please try again.') })
      .finally(() => setLoading(false))
  }, [filtersKey])

  useEffect(() => { load() }, [load])
  return { jobs, total, loading, error, refetch: load }
}
