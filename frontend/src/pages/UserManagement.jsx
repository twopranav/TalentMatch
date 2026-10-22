import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useAuth } from '../context/AuthContext'
import { useSearchParams } from 'react-router-dom'
import { useUsers } from '../hooks/useUsers'
import { useToast } from '../components/ui/Toast'
import Spinner from '../components/ui/Spinner'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import Modal from '../components/ui/Modal'
import PageHeader from '../components/ui/PageHeader'
import StatusBadge from '../components/ui/StatusBadge'
import Pagination from '../components/ui/Pagination'
import { setUserActive, setUserRole, transferSuperuser, deleteUser, approveRequest, rejectRequest, setUserSubCompany, updateUser } from '../api/users'
import Button from '../components/ui/Button'
import ProfileFields from '../components/profile/ProfileFields'
import { toFormState, toPayload } from '../utils/profileForm'
import { formatEnumLabel, getErrorMessage } from '../utils/format'
import { SUB_COMPANIES } from '../utils/subCompany'


const DIALOG_COPY = {
  deactivate: { title: 'Deactivate this user?', message: (u) => `${u.email} will lose access until reactivated.`, confirmLabel: 'Deactivate', destructive: true },
  activate: { title: 'Approve this user?', message: (u) => `${u.email} will be granted access immediately.`, confirmLabel: 'Approve' },
  approveRequest: { title: 'Approve access request?', message: (u) => `${u.email} will become ${u.requested_role} in ${u.sub_company || 'their sub company'}. The role and sub company are granted together.`, confirmLabel: 'Approve' },
  reject: { title: 'Reject access request?', message: (u) => `${u.email}'s request to become ${u.requested_role} will be declined. Their account is not otherwise affected.`, confirmLabel: 'Reject', destructive: true },
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
  const [pos, setPos] = useState(null)
  const ref = useRef(null)
  const menuRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const close = () => setOpen(false)
    const handleClick = (e) => {
      if (ref.current?.contains(e.target) || menuRef.current?.contains(e.target)) return
      setOpen(false)
    }
    const handleKey = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [open])

  // The menu is rendered in a portal with fixed positioning so a parent's
  // overflow (table card, page container) can never clip it. It flips above
  // the button when there isn't enough room below.
  useLayoutEffect(() => {
    if (!open) {
      setPos(null)
      return
    }
    const btn = ref.current?.getBoundingClientRect()
    const menu = menuRef.current?.getBoundingClientRect()
    if (!btn || !menu) return
    const gap = 4
    const openUp = btn.bottom + gap + menu.height > window.innerHeight && btn.top - gap - menu.height > 0
    setPos({
      top: openUp ? btn.top - gap - menu.height : btn.bottom + gap,
      left: Math.max(8, btn.right - menu.width),
    })
  }, [open])

  const isSelf = u.id === currentUser?.id
  const isTargetSuperuser = u.role === 'superuser'
  const hasPendingRequest = Boolean(u.requested_role)

  if (!isAdminOrSuperuser || isTargetSuperuser) {
    return <span className="text-xs text-slate-400 dark:text-slate-500">—</span>
  }

  const items = []
  // Mirrors backend _assert_can_edit_profile: superuser edits anyone, an admin only user/recruiter accounts.
  if (isSuperuser || u.role === 'user' || u.role === 'recruiter') {
    items.push({ key: 'edit', label: 'Edit profile', style: 'default' })
  }
  if (u.is_active) {
    items.push({ key: 'deactivate', label: 'Deactivate', style: 'destructive' })
  } else {
    items.push({ key: 'activate', label: 'Approve', style: 'accent' })
  }
  if (isSuperuser && hasPendingRequest) {
    items.push({ key: 'approveRequest', label: `Approve as ${u.requested_role}`, style: 'accent' })
    items.push({ key: 'reject', label: 'Reject request', style: 'destructive' })
  }
  if (isSuperuser) {
    items.push({ key: 'subCompany', label: 'Change sub company', style: 'default' })
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

      {open &&
        createPortal(
          <div
            ref={menuRef}
            role="menu"
            style={{
              position: 'fixed',
              top: pos?.top ?? 0,
              left: pos?.left ?? 0,
              visibility: pos ? 'visible' : 'hidden',
            }}
            className="z-50 w-44 overflow-hidden rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-700 dark:bg-slate-900"
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
          </div>,
          document.body
        )}
    </div>
  )
}

function UserDetailsModal({ user, onClose }) {
  if (!user) return null
  const rows = [
    ['Email', user.email],
    ['Phone', user.phone || '—'],
    ['Role', formatEnumLabel(user.role)],
    ['Requested role', user.requested_role ? formatEnumLabel(user.requested_role) : '—'],
    ['Status', user.is_active ? 'Active' : 'Inactive'],
    ['Sub company', user.sub_company || '—'],
    ['Company', user.company || '—'],
    ['Title', user.title || '—'],
    ['Skills', user.skills?.length ? user.skills.join(', ') : '—'],
    ['Experience (years)', user.experience_years ?? '—'],
    ['Location', user.location || '—'],
    ['Desired role', user.desired_role || '—'],
    ['Last login', user.last_login_at ? new Date(user.last_login_at).toLocaleString() : 'Never'],
    ['Created at', user.created_at ? new Date(user.created_at).toLocaleString() : '—'],
  ]
  return (
    <Modal open={Boolean(user)} onClose={onClose} title={user.full_name || user.email} size="md">
      {user.requested_role && <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-200">Access request pending · {formatEnumLabel(user.requested_role)}{user.sub_company ? ` · ${user.sub_company}` : ''}</div>}
      <dl className="grid grid-cols-[minmax(8rem,0.7fr)_minmax(0,1.3fr)] gap-x-5 gap-y-3 text-sm">
        {rows.map(([label, value]) => <div key={label} className="contents"><dt className="text-slate-500 dark:text-slate-400">{label}</dt><dd className="break-words text-right font-medium text-slate-900 dark:text-slate-100">{value}</dd></div>)}
      </dl>
      <p className="mt-5 border-t border-slate-200 pt-3 font-mono text-[11px] text-slate-400 dark:border-slate-700 dark:text-slate-500">User ID: {user.id}</p>
    </Modal>
  )
}

const USER_PAGE_SIZE = 25
const ROLE_OPTIONS = ['user', 'recruiter', 'admin', 'superuser']

export default function UserManagement() {
  const { user: currentUser, logout } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [tab, setTab] = useState(() => searchParams.get('pending') === 'true' ? 'pending' : 'all')
  const { users, loading, error, refetch } = useUsers(tab === 'pending')
  const { showToast } = useToast()
  const [busyId, setBusyId] = useState(null)
  const [pendingAction, setPendingAction] = useState(null)
  const [selectedUser, setSelectedUser] = useState(null)
  const [subTarget, setSubTarget] = useState(null)
  const [subValue, setSubValue] = useState('')
  const [editTarget, setEditTarget] = useState(null)
  const [editForm, setEditForm] = useState(() => toFormState(null))
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [page, setPage] = useState(1)

  const isSuperuser = currentUser?.role === 'superuser'
  const isAdminOrSuperuser = currentUser?.role === 'admin' || isSuperuser
  const filteredUsers = users.filter((candidate) => {
    const term = search.trim().toLowerCase()
    const matchesSearch = !term || [candidate.full_name, candidate.name, candidate.email, candidate.id].some((value) => String(value ?? '').toLowerCase().includes(term))
    return matchesSearch && (!roleFilter || candidate.role === roleFilter)
  })
  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / USER_PAGE_SIZE))
  const pageUsers = filteredUsers.slice((page - 1) * USER_PAGE_SIZE, page * USER_PAGE_SIZE)

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
    else if (type === 'approveRequest') runAction(target.id, () => approveRequest(target.id), `User approved as ${target.requested_role}.`, 'Could not approve request.')
    else if (type === 'reject') runAction(target.id, () => rejectRequest(target.id), 'Access request rejected.', 'Could not reject request.')
    else if (type === 'promote') runAction(target.id, () => setUserRole(target.id, 'admin'), 'User promoted to admin.', 'Could not promote user.')
    else if (type === 'demote') runAction(target.id, () => setUserRole(target.id, 'user'), 'Admin demoted to user.', 'Could not demote user.')
    else if (type === 'transfer') runAction(target.id, () => transferSuperuser(target.id), 'Superuser transferred.', 'Could not transfer superuser status.', logout)
    else if (type === 'delete') runAction(target.id, () => deleteUser(target.id), 'User deleted.', 'Could not delete user.')
  }

  const saveProfile = () => {
    if (!editTarget) return
    const target = editTarget
    runAction(target.id, () => updateUser(target.id, toPayload(editForm, target.role)), 'Profile updated.', 'Could not update this profile.', () => { setEditTarget(null); refetch() })
  }

  const saveSubCompany = () => {
    if (!subTarget || !subValue) return
    const target = subTarget
    runAction(target.id, () => setUserSubCompany(target.id, subValue), 'Sub company updated.', 'Could not update sub company.', () => { setSubTarget(null); refetch() })
  }

  return (
    <div className="mx-auto max-w-[1440px] px-8 py-8">
      <PageHeader eyebrow="Administration" title="User management" description="Review accounts, manage permissions, and review recruiter and admin access requests. Only the superuser can approve requests or change a sub company." />

        {isAdminOrSuperuser && (
          <div className="mb-4 flex gap-2" role="tablist" aria-label="User views">
            {['all', 'pending'].map((t) => (
              <button
                key={t}
                onClick={() => {
                  setTab(t)
                  setPage(1)
                  const next = new URLSearchParams(searchParams)
                  if (t === 'pending') next.set('pending', 'true')
                  else next.delete('pending')
                  setSearchParams(next)
                }}
                role="tab"
                aria-selected={tab === t}
                className={`rounded-xl px-3.5 py-2 text-xs font-semibold transition ${
                  tab === t
                    ? 'bg-indigo-700 text-white shadow-sm'
                    : 'border border-slate-200 bg-white/80 text-slate-600 hover:border-indigo-200 hover:text-indigo-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:text-indigo-300'
                }`}
              >
                {t === 'pending' ? 'Pending requests' : 'All users'}
              </button>
            ))}
          </div>
        )}

      <div className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-[#fbfaf7]/90 p-3 dark:border-slate-800 dark:bg-slate-900/90">
        <label className="sr-only" htmlFor="users-search">Search users</label>
        <input id="users-search" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Search by name, email, or user ID" className="min-w-72 flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-500/15 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" />
        <label className="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400">Role
          <select value={roleFilter} onChange={(event) => { setRoleFilter(event.target.value); setPage(1) }} className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:ring-2 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200"><option value="">All roles</option>{ROLE_OPTIONS.map((role) => <option key={role} value={role}>{formatEnumLabel(role)}</option>)}</select>
        </label>
        <span className="ml-auto text-xs tabular-nums text-slate-500 dark:text-slate-400">{filteredUsers.length} {filteredUsers.length === 1 ? 'user' : 'users'}</span>
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
      ) : filteredUsers.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 px-6 py-16 text-center dark:border-slate-700">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {search || roleFilter ? 'No users match these filters.' : tab === 'pending' ? 'No pending access requests.' : 'No users to show yet.'}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-slate-200/80 bg-[#fbfaf7]/95 shadow-sm dark:border-slate-800 dark:bg-slate-900/90">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium uppercase text-slate-500 dark:border-slate-800 dark:bg-slate-800/50 dark:text-slate-400">
              <tr>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Sub company</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Request</th>
                <th className="px-4 py-3">Last login</th>
                {isAdminOrSuperuser && <th className="px-4 py-3 text-right">Actions</th>}
                <th className="px-4 py-3 text-right">Details</th>
              </tr>
            </thead>
            <tbody>
              {pageUsers.map((u) => {
                const busy = busyId === u.id

                return (
                  <tr key={u.id} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                    <td className="px-4 py-3"><p className="font-medium text-slate-900 dark:text-slate-100">{u.full_name || u.name || '—'}</p><p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{u.email}</p></td>
                    <td className="px-4 py-3"><StatusBadge status={u.role}>{formatEnumLabel(u.role)}</StatusBadge></td>
                    <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-300">{u.sub_company || <span className="text-slate-400">—</span>}</td>
                    <td className="px-4 py-3"><StatusBadge status={u.is_active ? 'active' : 'inactive'}>{u.is_active ? 'Active' : 'Inactive'}</StatusBadge></td>
                    <td className="px-4 py-3">{u.requested_role ? <StatusBadge status="pending" tone="warning">{formatEnumLabel(u.requested_role)} requested</StatusBadge> : <span className="text-xs text-slate-400">—</span>}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-500 dark:text-slate-400">{(u.last_login_at ?? u.last_login) ? new Date(u.last_login_at ?? u.last_login).toLocaleString() : 'Never'}</td>
                    {isAdminOrSuperuser && (
                      <td className="px-4 py-3 text-right">
                        <UserActionsMenu
                          user={u}
                          currentUser={currentUser}
                          isSuperuser={isSuperuser}
                          isAdminOrSuperuser={isAdminOrSuperuser}
                          busy={busy}
                          onSelect={(type) => { if (type === 'subCompany') { setSubTarget(u); setSubValue(u.sub_company || '') } else if (type === 'edit') { setEditTarget(u); setEditForm(toFormState(u)) } else setPendingAction({ type, target: u }) }}
                        />
                      </td>
                    )}
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setSelectedUser(u)}
                        className="rounded-lg border border-slate-200 bg-[#fbfaf7] px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-indigo-200 hover:bg-white hover:text-indigo-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
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

      {!loading && !error && <div className="mt-4 flex items-center justify-between"><p className="text-xs text-slate-500 dark:text-slate-400">Showing {filteredUsers.length ? (page - 1) * USER_PAGE_SIZE + 1 : 0}–{Math.min(page * USER_PAGE_SIZE, filteredUsers.length)} of {filteredUsers.length} users</p><Pagination page={page} totalPages={totalPages} onPageChange={setPage} disabled={loading} /></div>}

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

      <Modal
        open={Boolean(editTarget)}
        onClose={() => setEditTarget(null)}
        title="Edit profile"
        size="md"
        footer={<>
          <Button variant="secondary" onClick={() => setEditTarget(null)}>Cancel</Button>
          <Button onClick={saveProfile} disabled={!editTarget || busyId === editTarget?.id}>{editTarget && busyId === editTarget.id ? 'Saving…' : 'Save'}</Button>
        </>}
      >
        {editTarget && (
          <div>
            <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">{editTarget.email} · {formatEnumLabel(editTarget.role)}</p>
            <ProfileFields role={editTarget.role} form={editForm} onChange={setEditForm} idPrefix="admin-edit" />
            <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">Role, active status and sub company are changed from the Actions menu.</p>
          </div>
        )}
      </Modal>

      {isSuperuser && (
        <Modal open={Boolean(subTarget)} onClose={() => setSubTarget(null)} title="Change sub company" size="md">
          {subTarget && (
            <div>
              <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">{subTarget.email} · currently {subTarget.sub_company || 'not assigned'}</p>
              <label htmlFor="assign-sub-company" className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-200">Sub company</label>
              <select id="assign-sub-company" value={subValue} onChange={(e) => setSubValue(e.target.value)} className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100">
                <option value="">Select a sub company</option>
                {SUB_COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Jobs keep the sub company they were posted under; they do not move with the person.</p>
              <div className="mt-5 flex justify-end gap-2">
                <button type="button" onClick={() => setSubTarget(null)} className="rounded border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">Cancel</button>
                <button type="button" onClick={saveSubCompany} disabled={!subValue || subValue === subTarget.sub_company || busyId === subTarget.id} className="rounded bg-slate-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50 dark:bg-slate-700">Save</button>
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}