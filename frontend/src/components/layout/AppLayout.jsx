// frontend/src/components/layout/AppLayout.jsx
import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import ThemeToggle from '../ui/ThemeToggle'

const navClass = ({ isActive }) =>
  `rounded-lg px-3 py-1.5 text-sm font-medium transition ${
    isActive
      ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
  }`

export default function AppLayout({ children }) {
  const { user, logout } = useAuth()
  const canViewUsers = ['recruiter', 'admin', 'superuser'].includes(user?.role)
  const isApplicant = user?.role === 'user'

  return (
    <div className="app-bg min-h-screen">
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/80 px-6 py-2.5 backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/80">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2" aria-label="TalentMatch home">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-linear-to-br from-indigo-500 to-indigo-700 text-xs font-bold text-white shadow-sm">
                T
              </span>
              <span className="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100">
                TalentMatch
              </span>
            </Link>

            <nav className="flex items-center gap-1">
              <NavLink to="/" end className={navClass}>Jobs</NavLink>
              <NavLink to="/profile" className={navClass}>Profile</NavLink>
              {isApplicant && <NavLink to="/applied-jobs" className={navClass}>Applied Jobs</NavLink>}
              {canViewUsers && <NavLink to="/my-jobs" className={navClass}>My Jobs</NavLink>}
              {canViewUsers && <NavLink to="/resumes" className={navClass}>Resumes</NavLink>}
              {canViewUsers && <NavLink to="/users" className={navClass}>Users</NavLink>}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {user?.role && (
              <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium capitalize text-indigo-700 ring-1 ring-inset ring-indigo-100 dark:bg-indigo-500/15 dark:text-indigo-300 dark:ring-indigo-500/20">
                {user.role}
              </span>
            )}
            <ThemeToggle />
            <button
              onClick={logout}
              className="rounded-lg px-2.5 py-1.5 text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            >
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="overflow-y-auto">{children}</main>
    </div>
  )
}