import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import AppLayout from './layout/AppLayout'

export default function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth()
  const location = useLocation()
  if (!isAuthenticated) {
    const returnTo = `${location.pathname}${location.search}${location.hash}`
    if (returnTo !== '/login' && !returnTo.startsWith('/login?')) sessionStorage.setItem('talentmatch:returnTo', returnTo)
    return <Navigate to="/login" replace />
  }
  return <AppLayout>{children}</AppLayout>
}
