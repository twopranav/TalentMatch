// frontend/src/components/layout/AppLayout.jsx
import { Link } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import ThemeToggle from '../ui/ThemeToggle'

export default function AppLayout({ children }) {
  const { user, logout } = useAuth()
  const canViewUsers = ['recruiter', 'admin', 'superuser'].includes(user?.role)
  const isApplicant = user?.role === 'user'

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white px-6 py-3 dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-6">
            <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">TalentMatch</span>
            <nav className="flex gap-4 text-sm text-slate-600 dark:text-slate-400">
              <Link to="/" className="hover:text-slate-900 dark:hover:text-slate-100">Jobs</Link>
              <Link to="/profile" className="hover:text-slate-900 dark:hover:text-slate-100">Profile</Link>
              {isApplicant && <Link to="/applied-jobs" className="hover:text-slate-900 dark:hover:text-slate-100">Applied Jobs</Link>}
              {canViewUsers && <Link to="/my-jobs" className="hover:text-slate-900 dark:hover:text-slate-100">My Jobs</Link>}
              {canViewUsers && <Link to="/resumes" className="hover:text-slate-900 dark:hover:text-slate-100">Resumes</Link>}
              {canViewUsers && <Link to="/users" className="hover:text-slate-900 dark:hover:text-slate-100">Users</Link>}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {user?.role && (
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium capitalize text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {user.role}
              </span>
            )}
            <ThemeToggle />
            <button onClick={logout} className="text-sm font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100">
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="overflow-y-auto">{children}</main>
    </div>
  )
}