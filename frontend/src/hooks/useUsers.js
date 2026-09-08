// frontend/src/hooks/useUsers.js
import { useCallback, useEffect, useState } from 'react'
import { fetchUsers } from '../api/users'

export function useUsers(pending = false) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    fetchUsers(pending)
      .then(setUsers)
      .catch((err) => {
        const message =
          err.response?.status === 403
            ? 'You do not have permission to view this.'
            : err.response?.status === 401
            ? 'Your session has expired. Please log in again.'
            : 'Could not load users. Please try again.'
        setError(message)
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending])

  useEffect(() => {
    load()
  }, [load])

  return { users, loading, error, refetch: load }
}