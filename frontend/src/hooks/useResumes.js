import { useCallback, useEffect, useState } from 'react'
import { fetchMyResumes } from '../api/resumes'

export function useResumes({ enabled = true } = {}) {
  const [resumes, setResumes] = useState([])
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    fetchMyResumes()
      .then(setResumes)
      .catch((err) => {
        const message =
          err.response?.status === 401
            ? 'Your session has expired. Please log in again.'
            : 'Could not load your resume. Please try again.'
        setError(message)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!enabled) return
    load()
  }, [enabled, load])

  return { resumes, loading, error, refetch: load }
}