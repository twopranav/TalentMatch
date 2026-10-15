import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import ThemeToggle from '../ui/ThemeToggle'
import { fetchUsers } from '../../api/users'
import { fetchLLMConfigs } from '../../api/llmConfig'
import ActionMenu from '../ui/ActionMenu'
import { DecoBackdrop, Flourish } from '../ui/Ornaments'
import emmveeLogo from '../../assets/emmvee-logo.jpg'

const navClass = ({ isActive }) => `relative px-3 py-2 text-sm font-medium transition after:absolute after:inset-x-3 after:-bottom-0.5 after:h-0.5 after:rounded-full after:transition-opacity ${isActive ? 'text-indigo-700 after:bg-indigo-600 after:opacity-100 dark:text-indigo-300 dark:after:bg-indigo-400' : 'text-slate-500 after:bg-indigo-500 after:opacity-0 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'}`
const ADMIN_ROLES = ['admin', 'superuser']
const MANAGER_ROLES = ['recruiter', 'admin', 'superuser']

function roleLabel(role) {
  return ({ user: 'Applicant', recruiter: 'Recruiter', admin: 'Administrator', superuser: 'Superuser' })[role] ?? 'Member'
}

export default function AppLayout({ children }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const role = user?.role
  const canManage = MANAGER_ROLES.includes(role)
  const isAdmin = ADMIN_ROLES.includes(role)
  const isApplicant = role === 'user'
  const [pendingRequests, setPendingRequests] = useState(0)
  const [unsetModels, setUnsetModels] = useState([])
  const displayName = user?.name || user?.full_name || user?.email?.split('@')[0] || 'Account'
  const initials = displayName.split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase()

  const loadPendingRequests = useCallback(async () => {
    if (!isAdmin) return
    try {
      const result = await fetchUsers(true)
      const rows = Array.isArray(result) ? result : (result?.items ?? result?.results ?? result?.users ?? [])
      setPendingRequests(Number(result?.pending_count ?? result?.total ?? rows.length))
    } catch { /* preserve last known badge count */ }
  }, [isAdmin])
  const loadUnsetModels = useCallback(async () => {
    if (!isAdmin) return
    try {
      const result = await fetchLLMConfigs()
      const rows = Array.isArray(result) ? result : (result?.items ?? result?.configs ?? result?.results ?? [])
      setUnsetModels(rows.filter((row) => !row.model || !String(row.model).trim()).map((row) => row.task ?? row.name).filter(Boolean))
    } catch { setUnsetModels([]) }
  }, [isAdmin])

  useEffect(() => {
    loadPendingRequests(); loadUnsetModels()
    if (!isAdmin) return undefined
    const interval = window.setInterval(() => { loadPendingRequests(); loadUnsetModels() }, 60000)
    window.addEventListener('focus', loadPendingRequests)
    return () => { window.clearInterval(interval); window.removeEventListener('focus', loadPendingRequests) }
  }, [isAdmin, loadPendingRequests, loadUnsetModels])

  const logoutAndNavigate = async () => { await logout(); navigate('/login', { replace: true }) }
  const menuItems = [
    { label: 'My profile', onSelect: () => navigate('/profile') },
    { label: 'Log out', danger: true, onSelect: logoutAndNavigate },
  ]

  return <div className="app-bg min-h-screen">
    <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-slate-50/90 px-6 py-3 backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-950/90">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-8">
        <div className="flex min-w-0 items-center gap-7">
          <Link to="/" className="flex shrink-0 items-center" aria-label="Emmvee home">
            <img src={emmveeLogo} alt="Emmvee" className="h-10 w-auto rounded-sm bg-white px-1" />
          </Link>
          <nav aria-label="Primary navigation" className="flex items-center gap-1">
            <NavLink to="/" end className={navClass}>Overview</NavLink>
            <NavLink to="/jobs" className={navClass}>Jobs</NavLink>
            {canManage && <NavLink to="/resumes" className={navClass}>Resume library</NavLink>}
            {isAdmin && <NavLink to="/admin/llm" className={navClass}>LLM Config</NavLink>}
            {isAdmin && <ActionMenu label="Admin navigation" align="start" items={[
              { label: 'Access requests', badge: pendingRequests, onSelect: () => navigate('/users?pending=true') },
              { label: 'User management', onSelect: () => navigate('/users') },
              { label: 'Audit feed', onSelect: () => navigate('/audit') },
            ]} />}
            {role === 'recruiter' && <NavLink to="/audit" className={navClass}>Audit feed</NavLink>}
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <ThemeToggle />
          <ActionMenu label={`Account menu for ${displayName}`} items={menuItems} trigger={<span className="flex items-center gap-2 rounded-xl px-2 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800">
            {user?.avatar_url ? <img src={user.avatar_url} alt="" className="h-9 w-9 rounded-full object-cover ring-1 ring-slate-200 dark:ring-slate-700" /> : <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">{initials}</span>}
            <span className="max-w-40 text-left"><span className="block truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{displayName}</span><span className="block text-xs text-slate-500 dark:text-slate-400">{roleLabel(role)}</span></span><span aria-hidden="true" className="ml-1 text-xs text-slate-400">⌄</span>
          </span>} />
        </div>
      </div>
      {(location.pathname.startsWith('/jobs') || location.pathname === '/jobs') && <div className="mx-auto mt-2 flex max-w-[1440px] items-center gap-2 border-t border-slate-200/70 pt-2 dark:border-slate-800/70">
        <span className="mr-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Workspace</span>
        <NavLink to="/jobs" end className={({ isActive }) => `rounded-md px-2.5 py-1 text-xs font-medium ${isActive ? 'bg-indigo-50 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200' : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'}`}>All jobs</NavLink>
        {isApplicant && <NavLink to="/jobs/applied" className={({ isActive }) => `rounded-md px-2.5 py-1 text-xs font-medium ${isActive ? 'bg-indigo-50 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200' : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'}`}>Applied</NavLink>}
        {canManage && <NavLink to="/jobs/mine" className={({ isActive }) => `rounded-md px-2.5 py-1 text-xs font-medium ${isActive ? 'bg-indigo-50 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200' : 'text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'}`}>My jobs</NavLink>}
      </div>}
    </header>

    {isAdmin && unsetModels.length > 0 && <div role="status" className="border-b border-amber-300 bg-amber-50 px-6 py-2.5 dark:border-amber-900 dark:bg-amber-950/60">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 text-sm text-amber-900 dark:text-amber-200">
        <span><strong>LLM configuration needs attention.</strong> No model is set for {unsetModels.join(', ')}.</span>
        <Link to="/admin/llm" className="shrink-0 font-semibold underline underline-offset-2">Configure models →</Link>
      </div>
    </div>}

    <main className="relative overflow-y-auto"><DecoBackdrop /><div className="relative">{children}</div></main>
    <footer className="relative mx-auto max-w-[1440px] px-6 pb-10 pt-6 text-center" aria-hidden="true"><Flourish className="mx-auto h-4 w-52 text-gold-500/70 dark:text-gold-400/50" /><p className="font-display mt-2 text-xs font-semibold uppercase tracking-[0.35em] text-slate-400 dark:text-slate-600">Emmvee</p></footer>
  </div>
}
