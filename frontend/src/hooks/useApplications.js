import { useCallback, useEffect, useState } from 'react'
import { fetchMyApplications } from '../api/applications'

export function useMyApplications(enabled = true) {
  const [applications, setApplications] = useState([])
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    if (!enabled) return
    setLoading(true)
    setError(null)
    fetchMyApplications()
      .then(setApplications)
      .catch(() => setError('Could not load your applications.'))
      .finally(() => setLoading(false))
  }, [enabled])

  useEffect(() => {
    load()
  }, [load])

  return { applications, loading, error, refetch: load }
}