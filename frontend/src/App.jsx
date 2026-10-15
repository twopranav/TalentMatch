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
import AuditHistory from './pages/AuditHistory'
import LLMSettings from './pages/LLMSettings'
import Overview from './pages/Overview'

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
    <BrowserRouter
  future={{
    v7_startTransition: true,
    v7_relativeSplatPath: true,
      }}
    >
      <Routes>
        <Route path="/login" element={<LoginRoute />} />

        <Route path="/register" element={<RegisterRoute />} />

        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Overview />
            </ProtectedRoute>
          }
        />

        <Route
          path="/jobs"
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
          path="/jobs/applied"
          element={
            <ProtectedRoute>
              <RequireRole roles={['user']}>
                <AppliedJobs />
              </RequireRole>
            </ProtectedRoute>
          }
        />

        <Route
          path="/jobs/mine"
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

        <Route path="/my-jobs" element={<Navigate to="/jobs/mine" replace />} />
        <Route path="/applied-jobs" element={<Navigate to="/jobs/applied" replace />} />

        <Route
          path="/users"
          element={
            <ProtectedRoute>
              <RequireRole roles={['admin', 'superuser']}>
                <UserManagement />
              </RequireRole>
            </ProtectedRoute>
          }
        />

        <Route
          path="/audit"
          element={
            <ProtectedRoute>
              <RequireRole roles={['recruiter', 'admin', 'superuser']}>
                <AuditHistory />
              </RequireRole>
            </ProtectedRoute>
          }
        />

        <Route
          path="/admin/llm"
          element={
            <ProtectedRoute>
              <RequireRole roles={['admin', 'superuser']}>
                <LLMSettings />
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