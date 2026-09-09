import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useUsers } from '../hooks/useUsers'
import { useToast } from '../components/ui/Toast'
import Spinner from '../components/ui/Spinner'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import { setUserActive, setUserRole, transferSuperuser, deleteUser, rejectRecruiterRequest } from '../api/users'
import { getErrorMessage } from '../utils/format'

const ROLE_STYLES = {
  superuser: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300',
  admin: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  recruiter: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  user: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
}

const DIALOG_COPY = {
  deactivate: { title: 'Deactivate this user?', message: (u) => `${u.email} will lose access until reactivated.`, confirmLabel: 'Deactivate', destructive: true },
  activate: { title: 'Approve this user?', message: (u) => `${u.email} will be granted access immediately.`, confirmLabel: 'Approve' },
  reject: { title: 'Reject recruiter request?', message: (u) => `${u.email}'s request to become a recruiter will be declined. Their account is not otherwise affected.`, confirmLabel: 'Reject', destructive: true },
  promote: { title: 'Promote to admin?', message: (u) => `${u.email} will gain full admin permissions.`, confirmLabel: 'Promote' },
  demote: { title: 'Demote to user?', message: (u) => `${u.email} will lose admin permissions.`, confirmLabel: 'Demote', destructive: true },
  transfer: { title: 'Transfer superuser status?', message: (u) => `You will become a regular user and ${u.email} will become the sole superuser. You'll be logged out immediately after.`, confirmLabel: 'Transfer', destructive: true },
  delete: { title: 'Delete this user?', message: (u) => `${u.email} will be permanently removed. This can't be undone.`, confirmLabel: 'Delete', destructive: true },
}

const MENU_ITEM_STYLES = {
  default: 'text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800',
  destructive: 'text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950',
  accent: 'text-emerald-700 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-950',
}

function ChevronIcon({ open }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-180' : ''}`}
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  )
}

function UserActionsMenu({ user: u, currentUser, isSuperuser, isAdminOrSuperuser, busy, onSelect }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    const handleKey = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  const isSelf = u.id === currentUser?.id
  const isTargetSuperuser = u.role === 'superuser'
  const hasPendingRequest = Boolean(u.requested_role)

  if (!isAdminOrSuperuser || isTargetSuperuser) {
    return <span className="text-xs text-slate-400 dark:text-slate-500">—</span>
  }

  const items = []
  if (u.is_active) {
    items.push({ key: 'deactivate', label: 'Deactivate', style: 'destructive' })
  } else {
    items.push({ key: 'activate', label: 'Approve', style: 'accent' })
  }
  if (hasPendingRequest) {
    items.push({ key: 'reject', label: 'Reject request', style: 'destructive' })
  }
  if (isSuperuser) {
    items.push(
      u.role === 'admin'
        ? { key: 'demote', label: 'Demote to user', style: 'default' }
        : { key: 'promote', label: 'Promote to admin', style: 'default' }
    )
    if (!isSelf) {
      items.push({ key: 'transfer', label: 'Make superuser', style: 'default' })
    }
  }
  items.push({ key: 'delete', label: 'Delete user', style: 'destructive' })

  const select = (key) => {
    setOpen(false)
    onSelect(key)
  }

  return (
    <div className="relative inline-block text-left" ref={ref}>
      <button
        type="button"
        disabled={busy}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
      >
        {busy ? <Spinner size="sm" label="Working" /> : (
          <>
            Actions
            <ChevronIcon open={open} />
          </>
        )}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-1 w-44 overflow-hidden rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-900"
        >
          {items.map((item) => (
            <button
              key={item.key}
              role="menuitem"
              onClick={() => select(item.key)}
              className={`block w-full px-3 py-2 text-left text-xs font-medium ${MENU_ITEM_STYLES[item.style]}`}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function UserDetailsModal({ user, onClose }) {
  if (!user) return null

  const hasPendingRequest = Boolean(user.requested_role)

  const rows = [
    ['Email', user.email],
    ['Phone', user.phone || '—'],
    ['Role', user.role],
    ['Requested role', user.requested_role || '—'],
    ['Status', user.is_active ? 'Active' : 'Pending'],
    ['Company', user.company || '—'],
    ['Title', user.title || '—'],
    ['Skills', user.skills?.length ? user.skills.join(', ') : '—'],
    ['Experience (years)', user.experience_years ?? '—'],
    ['Location', user.location || '—'],
    ['Desired role', user.desired_role || '—'],
    ['Last login', user.last_login_at ? new Date(user.last_login_at).toLocaleString() : '—'],
    ['Created at', user.created_at ? new Date(user.created_at).toLocaleString() : '—'],
  ]

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-6 shadow-xl dark:border-slate-700 dark:bg-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            {user.full_name || user.email}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300"
          >
            ✕
          </button>
        </div>

        {hasPendingRequest && (
          <div className="mb-3 rounded bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
            Requested: {user.requested_role}
          </div>
        )}

        <dl className="space-y-2 text-sm">
          {rows.map(([label, value]) => (
            <div key={label} className="flex justify-between gap-4">
              <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
              <dd className="text-right text-slate-900 dark:text-slate-100">{value}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-3 border-t border-slate-100 pt-3 text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
          User ID: {user.id}
        </div>
      </div>
    </div>
  )
}

export default function UserManagement() {
  const { user: currentUser, logout } = useAuth()
  const [tab, setTab] = useState('all')
  const { users, loading, error, refetch } = useUsers(tab === 'pending')
  const { showToast } = useToast()
  const [busyId, setBusyId] = useState(null)
  const [pendingAction, setPendingAction] = useState(null)
  const [selectedUser, setSelectedUser] = useState(null)

  const isSuperuser = currentUser?.role === 'superuser'
  const isAdminOrSuperuser = currentUser?.role === 'admin' || isSuperuser

  const runAction = async (targetId, fn, successMessage, errorMessage, afterSuccess) => {
    setBusyId(targetId)
    try {
      await fn()
      showToast(successMessage, 'success')
      afterSuccess ? afterSuccess() : refetch()
    } catch (err) {
      showToast(getErrorMessage(err, errorMessage), 'error')
    } finally {
      setBusyId(null)
      setPendingAction(null)
    }
  }

  const confirmAction = () => {
    if (!pendingAction) return
    const { type, target } = pendingAction
    if (type === 'deactivate') runAction(target.id, () => setUserActive(target.id, false), 'User deactivated.', 'Could not deactivate user.')
    else if (type === 'activate') runAction(target.id, () => setUserActive(target.id, true), 'User approved.', 'Could not approve user.')
    else if (type === 'reject') runAction(target.id, () => rejectRecruiterRequest(target.id), 'Recruiter request rejected.', 'Could not reject request.')
    else if (type === 'promote') runAction(target.id, () => setUserRole(target.id, 'admin'), 'User promoted to admin.', 'Could not promote user.')
    else if (type === 'demote') runAction(target.id, () => setUserRole(target.id, 'user'), 'Admin demoted to user.', 'Could not demote user.')
    else if (type === 'transfer') runAction(target.id, () => transferSuperuser(target.id), 'Superuser transferred.', 'Could not transfer superuser status.', logout)
    else if (type === 'delete') runAction(target.id, () => deleteUser(target.id), 'User deleted.', 'Could not delete user.')
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">User Management</h1>

        {isAdminOrSuperuser && (
          <div className="flex gap-2">
            {['all', 'pending'].map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded px-3 py-1.5 text-sm font-medium ${
                  tab === t
                    ? 'bg-slate-800 text-white dark:bg-slate-700'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                }`}
              >
                {t === 'pending' ? 'Pending requests' : 'All users'}
              </button>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading users" />
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-6 py-8 text-center dark:border-red-900 dark:bg-red-950">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          <button onClick={refetch} className="mt-3 text-sm font-medium text-red-800 underline hover:no-underline dark:text-red-300">
            Try again
          </button>
        </div>
      ) : users.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 px-6 py-16 text-center dark:border-slate-700">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {tab === 'pending' ? 'No pending recruiter requests.' : 'No users to show yet.'}
          </p>
        </div>
      ) : (
        <div className="overflow-visible rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium uppercase text-slate-500 dark:border-slate-800 dark:bg-slate-800/50 dark:text-slate-400">
              <tr>
                <th className="px-4 py-3">User ID</th>
                <th className="px-4 py-3">Name</th>
                {isAdminOrSuperuser && <th className="px-4 py-3 text-right">Actions</th>}
                <th className="px-4 py-3 text-right">View Details</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const busy = busyId === u.id

                return (
                  <tr key={u.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                    <td className="px-4 py-3 font-mono text-xs text-slate-500 dark:text-slate-400" title={u.id}>
                      {u.id.slice(0, 8)}…
                    </td>
                    <td className="px-4 py-3 text-slate-900 dark:text-slate-100">{u.full_name || '—'}</td>
                    {isAdminOrSuperuser && (
                      <td className="px-4 py-3 text-right">
                        <UserActionsMenu
                          user={u}
                          currentUser={currentUser}
                          isSuperuser={isSuperuser}
                          isAdminOrSuperuser={isAdminOrSuperuser}
                          busy={busy}
                          onSelect={(type) => setPendingAction({ type, target: u })}
                        />
                      </td>
                    )}
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setSelectedUser(u)}
                        className="rounded border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                      >
                        View details
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={Boolean(pendingAction)}
        onClose={() => setPendingAction(null)}
        onConfirm={confirmAction}
        title={pendingAction ? DIALOG_COPY[pendingAction.type].title : ''}
        message={pendingAction ? DIALOG_COPY[pendingAction.type].message(pendingAction.target) : ''}
        confirmLabel={pendingAction ? DIALOG_COPY[pendingAction.type].confirmLabel : 'Confirm'}
        destructive={pendingAction ? Boolean(DIALOG_COPY[pendingAction.type].destructive) : false}
      />

      <UserDetailsModal user={selectedUser} onClose={() => setSelectedUser(null)} />
    </div>
  )
}