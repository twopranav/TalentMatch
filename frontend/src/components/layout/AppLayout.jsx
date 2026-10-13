// frontend/src/components/layout/AppLayout.jsx
import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import ThemeToggle from '../ui/ThemeToggle'
import { Crest, DecoBackdrop, Flourish } from '../ui/Ornaments'

const navClass = ({ isActive }) =>
  `relative px-3 py-1.5 text-sm font-medium tracking-wide transition after:absolute after:inset-x-3 after:-bottom-1 after:h-0.5 after:rounded-full after:transition-opacity ${
    isActive
      ? 'text-indigo-800 after:bg-gold-500 after:opacity-100 dark:text-gold-300 dark:after:bg-gold-400'
      : 'text-slate-500 after:bg-gold-500 after:opacity-0 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'
  }`

export default function AppLayout({ children }) {
  const { user, logout } = useAuth()
  const canViewUsers = ['recruiter', 'admin', 'superuser'].includes(user?.role)
  const isAdmin = ['admin', 'superuser'].includes(user?.role)
  const isApplicant = user?.role === 'user'

  return (
    <div className="app-bg min-h-screen">
      <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-slate-50/85 px-6 py-3 backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-950/80">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2" aria-label="TalentMatch home">
              <Crest className="h-9 w-9 drop-shadow-sm" />
              <span className="font-display text-xl font-semibold tracking-wide text-slate-900 dark:text-slate-100">
                TalentMatch
              </span>
            </Link>

            <nav className="flex items-center gap-2">
              <NavLink to="/" end className={navClass}>Jobs</NavLink>
              <NavLink to="/profile" className={navClass}>Profile</NavLink>
              {isApplicant && <NavLink to="/applied-jobs" className={navClass}>Applied Jobs</NavLink>}
              {canViewUsers && <NavLink to="/my-jobs" className={navClass}>My Jobs</NavLink>}
              {canViewUsers && <NavLink to="/resumes" className={navClass}>Resumes</NavLink>}
              {canViewUsers && <NavLink to="/users" className={navClass}>Users</NavLink>}
              {canViewUsers && <NavLink to="/audit" className={navClass}>Audit</NavLink>}
              {isAdmin && <NavLink to="/admin/llm" className={navClass}>LLM</NavLink>}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {user?.role && (
              <span className="rounded-full bg-gold-50 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-widest text-gold-700 ring-1 ring-inset ring-gold-300/70 dark:bg-gold-400/10 dark:text-gold-300 dark:ring-gold-400/30">
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

      <main className="relative overflow-y-auto">
        <DecoBackdrop />
        <div className="relative">{children}</div>
      </main>

      <footer className="relative mx-auto max-w-5xl px-6 pb-10 pt-6 text-center" aria-hidden="true">
        <Flourish className="mx-auto h-4 w-52 text-gold-500/70 dark:text-gold-400/50" />
        <p className="font-display mt-2 text-xs font-semibold uppercase tracking-[0.35em] text-slate-400 dark:text-slate-600">
          TalentMatch
        </p>
      </footer>
    </div>
  )
}