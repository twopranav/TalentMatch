import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import AppLayout from './layout/AppLayout'
import FullPageSpinner from './ui/FullPageSpinner'

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()
  if (loading) return <FullPageSpinner />
  if (!isAuthenticated) {
    const returnTo = `${location.pathname}${location.search}${location.hash}`
    if (returnTo !== '/login' && !returnTo.startsWith('/login?')) sessionStorage.setItem('talentmatch:returnTo', returnTo)
    return <Navigate to="/login" replace />
  }
  return <AppLayout>{children}</AppLayout>
}
