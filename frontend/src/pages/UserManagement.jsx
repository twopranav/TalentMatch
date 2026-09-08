// frontend/src/pages/UserManagement.jsx
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useUsers } from '../hooks/useUsers'
import { useToast } from '../components/ui/Toast'
import Spinner from '../components/ui/Spinner'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import { setUserActive, setUserRole, transferSuperuser, deleteUser, rejectRecruiterRequest } from '../api/users'

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

export default function UserManagement() {
  const { user: currentUser, logout } = useAuth()
  // pending tab calls GET /api/users?pending=true, admin/superuser only —
  // backend 403s a recruiter for this filter, so the tab itself is hidden
  // from recruiters below.
  const [tab, setTab] = useState('all')
  const { users, loading, error, refetch } = useUsers(tab === 'pending')
  const { showToast } = useToast()
  const [busyId, setBusyId] = useState(null)
  const [pendingAction, setPendingAction] = useState(null)

  const isSuperuser = currentUser?.role === 'superuser'
  const isAdminOrSuperuser = currentUser?.role === 'admin' || isSuperuser

  const runAction = async (targetId, fn, successMessage, errorMessage, afterSuccess) => {
    setBusyId(targetId)
    try {
      await fn()
      showToast(successMessage, 'success')
      afterSuccess ? afterSuccess() : refetch()
    } catch (err) {
      showToast(err.response?.data?.detail || errorMessage, 'error')
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
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium uppercase text-slate-500 dark:border-slate-800 dark:bg-slate-800/50 dark:text-slate-400">
              <tr>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Status</th>
                {isAdminOrSuperuser && <th className="px-4 py-3">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const isSelf = u.id === currentUser?.id
                const isTargetSuperuser = u.role === 'superuser'
                const busy = busyId === u.id
                const hasPendingRequest = Boolean(u.requested_role)

                return (
                  <tr key={u.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                    <td className="px-4 py-3 text-slate-900 dark:text-slate-100">{u.email}</td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-400">{u.full_name || '—'}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${ROLE_STYLES[u.role]}`}>
                        {u.role}
                      </span>
                      {hasPendingRequest && (
                        <span className="ml-1.5 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                          Requested: {u.requested_role}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {'is_active' in u ? (
                        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${u.is_active ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}`}>
                          {u.is_active ? 'Active' : 'Pending'}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>

                    {isAdminOrSuperuser && (
                      <td className="px-4 py-3">
                        {isTargetSuperuser ? (
                          <span className="text-xs text-slate-400 dark:text-slate-500">—</span>
                        ) : (
                          <div className="flex flex-wrap gap-2">
                            {u.is_active ? (
                              <button disabled={busy} onClick={() => setPendingAction({ type: 'deactivate', target: u })} className="text-xs font-medium text-red-600 hover:underline disabled:opacity-50 dark:text-red-400">
                                Deactivate
                              </button>
                            ) : (
                              <button disabled={busy} onClick={() => setPendingAction({ type: 'activate', target: u })} className="text-xs font-medium text-emerald-700 hover:underline disabled:opacity-50 dark:text-emerald-400">
                                Approve
                              </button>
                            )}

                            {hasPendingRequest && (
                              <button disabled={busy} onClick={() => setPendingAction({ type: 'reject', target: u })} className="text-xs font-medium text-amber-700 hover:underline disabled:opacity-50 dark:text-amber-400">
                                Reject request
                              </button>
                            )}

                            {isSuperuser && (
                              u.role === 'admin' ? (
                                <button disabled={busy} onClick={() => setPendingAction({ type: 'demote', target: u })} className="text-xs font-medium text-slate-600 hover:underline disabled:opacity-50 dark:text-slate-400">
                                  Demote
                                </button>
                              ) : (
                                <button disabled={busy} onClick={() => setPendingAction({ type: 'promote', target: u })} className="text-xs font-medium text-blue-700 hover:underline disabled:opacity-50 dark:text-blue-400">
                                  Promote to admin
                                </button>
                              )
                            )}

                            {isSuperuser && !isSelf && (
                              <button disabled={busy} onClick={() => setPendingAction({ type: 'transfer', target: u })} className="text-xs font-medium text-purple-700 hover:underline disabled:opacity-50 dark:text-purple-400">
                                Make superuser
                              </button>
                            )}

                            <button disabled={busy} onClick={() => setPendingAction({ type: 'delete', target: u })} className="text-xs font-medium text-red-700 hover:underline disabled:opacity-50 dark:text-red-400">
                              Delete
                            </button>
                          </div>
                        )}
                      </td>
                    )}
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
    </div>
  )
}