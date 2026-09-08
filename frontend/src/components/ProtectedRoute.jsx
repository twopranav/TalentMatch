import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import AppLayout from './layout/AppLayout'

export default function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <AppLayout>{children}</AppLayout>
}