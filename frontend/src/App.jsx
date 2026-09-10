import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Login from './pages/Login'
import Register from './pages/Register'
import JobDashboard from './pages/JobDashboard'
import UserManagement from './pages/UserManagement'
import ProtectedRoute from './components/ProtectedRoute'
import RequireRole from './components/RequireRole'
import Profile from './pages/Profile'
import MyJobs from './pages/MyJobs'
import AppliedJobs from './pages/AppliedJobs'
import JobApplicants from './pages/JobApplicants'
import ResumeLibrary from './pages/ResumeLibrary'

function LoginRoute() {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <Navigate to="/" replace /> : <Login />
}

function RegisterRoute() {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <Navigate to="/" replace /> : <Register />
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />

        <Route path="/register" element={<RegisterRoute />} />

        <Route
          path="/"
          element={
            <ProtectedRoute>
              <JobDashboard />
            </ProtectedRoute>
          }
        />

        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <Profile />
            </ProtectedRoute>
          }
        />

        <Route
          path="/applied-jobs"
          element={
            <ProtectedRoute>
              <RequireRole roles={['user']}>
                <AppliedJobs />
              </RequireRole>
            </ProtectedRoute>
          }
        />

        <Route
          path="/my-jobs"
          element={
            <ProtectedRoute>
              <RequireRole roles={['recruiter', 'admin', 'superuser']}>
                <MyJobs />
              </RequireRole>
            </ProtectedRoute>
          }
        />

        <Route
          path="/jobs/:jobId/applicants"
          element={
            <ProtectedRoute>
              <RequireRole roles={['recruiter', 'admin', 'superuser']}>
                <JobApplicants />
              </RequireRole>
            </ProtectedRoute>
          }
        />

        <Route
          path="/resumes"
          element={
            <ProtectedRoute>
              <RequireRole roles={['recruiter', 'admin', 'superuser']}>
                <ResumeLibrary />
              </RequireRole>
            </ProtectedRoute>
          }
        />

        <Route
          path="/users"
          element={
            <ProtectedRoute>
              <RequireRole roles={['recruiter', 'admin', 'superuser']}>
                <UserManagement />
              </RequireRole>
            </ProtectedRoute>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App