import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { fetchMe, updateMe, uploadAvatar, changePassword, deleteMyAccount } from '../api/users'
import { deleteResume } from '../api/resumes'
import { useResumes } from '../hooks/useResumes'
import ResumeUploadModal from '../components/resume/ResumeUploadModal'
import ResumePreview from '../components/resume/ResumePreview'
import Spinner from '../components/ui/Spinner'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import Modal from '../components/ui/Modal'
import Button from '../components/ui/Button'
import Field from '../components/ui/Field'
import StatusBadge from '../components/ui/StatusBadge'
import { useToast } from '../components/ui/Toast'
import { getErrorMessage } from '../utils/format'

function emptyForm() {
  return { full_name: '', phone: '', company: '', title: '', skills: '', experience_years: '', location: '', desired_role: '' }
}

function toFormState(user = {}) {
  return {
    full_name: user.full_name || user.name || '',
    phone: user.phone || '',
    company: user.company || '',
    title: user.title || '',
    skills: Array.isArray(user.skills) ? user.skills.join(', ') : (user.skills || ''),
    experience_years: user.experience_years ?? '',
    location: user.location || '',
    desired_role: user.desired_role || '',
  }
}

function toPayload(form) {
  return {
    full_name: form.full_name.trim(),
    phone: form.phone.trim() || null,
    ...(form.company !== undefined ? { company: form.company.trim() || null } : {}),
    ...(form.title !== undefined ? { title: form.title.trim() || null } : {}),
    ...(form.location !== undefined ? { location: form.location.trim() || null } : {}),
    ...(form.desired_role !== undefined ? { desired_role: form.desired_role.trim() || null } : {}),
    skills: form.skills ? form.skills.split(',').map((skill) => skill.trim()).filter(Boolean) : [],
    experience_years: form.experience_years === '' ? null : Number(form.experience_years),
  }
}

function roleLabel(role) {
  return ({ user: 'Applicant', candidate: 'Applicant', recruiter: 'Recruiter', admin: 'Administrator', superuser: 'Superuser' })[role] ?? 'Member'
}

export default function Profile() {
  const { user: authUser, logout, refreshProfile } = useAuth()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)
  const [avatarUploading, setAvatarUploading] = useState(false)
  const [resumeModalOpen, setResumeModalOpen] = useState(false)
  const [resumeToDelete, setResumeToDelete] = useState(false)
  const [deletingResume, setDeletingResume] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [passwordForm, setPasswordForm] = useState({ current: '', next: '', confirm: '' })
  const [changingPassword, setChangingPassword] = useState(false)
  const [deleteAccountOpen, setDeleteAccountOpen] = useState(false)
  const [deletePassword, setDeletePassword] = useState('')
  const [deleteText, setDeleteText] = useState('')
  const [deletingAccount, setDeletingAccount] = useState(false)

  const role = profile?.role ?? authUser?.role
  const isCandidate = role === 'user' || role === 'candidate'
  const isRecruiter = role === 'recruiter'
  const isSuperuser = role === 'superuser'
  const { resumes, loading: resumesLoading, refetch: refetchResumes } = useResumes({ enabled: isCandidate })
  const currentResume = resumes[0] ?? null

  const loadProfile = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchMe()
      setProfile(data)
      setForm(toFormState(data))
    } catch (error) {
      showToast(getErrorMessage(error, 'Could not load your profile.'), 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => { loadProfile() }, [loadProfile])

  const set = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }))

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSaving(true)
    try {
      const updated = await updateMe(toPayload(form))
      setProfile((current) => ({ ...current, ...updated }))
      setForm(toFormState(updated))
      if (refreshProfile) await refreshProfile().catch(() => {})
      showToast('Profile updated.', 'success')
    } catch (error) {
      showToast(getErrorMessage(error, 'Could not update your profile.'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleAvatarChange = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setAvatarUploading(true)
    try {
      const updated = await uploadAvatar(file)
      setProfile((current) => ({ ...current, ...updated }))
      if (refreshProfile) {
        const fullProfile = await refreshProfile().catch(() => null)
        if (fullProfile) setProfile((current) => ({ ...current, ...fullProfile }))
      }
      showToast('Profile photo updated.', 'success')
    } catch (error) {
      showToast(getErrorMessage(error, 'Could not upload the photo.'), 'error')
    } finally {
      setAvatarUploading(false)
      event.target.value = ''
    }
  }

  const handleDeleteResume = async () => {
    if (!currentResume) return
    setDeletingResume(true)
    try {
      await deleteResume(currentResume.id)
      await refetchResumes()
      setResumeToDelete(false)
      showToast('Resume deleted.', 'success')
    } catch (error) {
      showToast(getErrorMessage(error, 'Could not delete your resume.'), 'error')
    } finally {
      setDeletingResume(false)
    }
  }

  const handleChangePassword = async (event) => {
    event.preventDefault()
    if (passwordForm.next.length < 8 || !/[a-z]/.test(passwordForm.next) || !/[A-Z]/.test(passwordForm.next) || !/[0-9]/.test(passwordForm.next)) {
      showToast('Use at least 8 characters with uppercase, lowercase, and a number.', 'error')
      return
    }
    if (passwordForm.next !== passwordForm.confirm) {
      showToast('The new passwords do not match.', 'error')
      return
    }
    setChangingPassword(true)
    try {
      await changePassword(passwordForm.current, passwordForm.next)
      setPasswordForm({ current: '', next: '', confirm: '' })
      showToast('Password changed successfully.', 'success')
    } catch (error) {
      showToast(getErrorMessage(error, 'Could not change your password.'), 'error')
    } finally {
      setChangingPassword(false)
    }
  }

  const handleDeleteAccount = async () => {
    if (!deletePassword || deleteText !== 'DELETE') return
    setDeletingAccount(true)
    try {
      await deleteMyAccount(deletePassword)
      setDeleteAccountOpen(false)
      showToast('Your account has been deleted.', 'success')
      await logout()
      navigate('/login', { replace: true })
    } catch (error) {
      showToast(getErrorMessage(error, 'Could not delete your account.'), 'error')
    } finally {
      setDeletingAccount(false)
    }
  }

  if (loading) return <div className="flex min-h-72 items-center justify-center"><Spinner label="Loading profile" /></div>
  if (!profile) return <section className="rounded-2xl border border-slate-200 bg-white p-8 dark:border-slate-800 dark:bg-slate-900"><h1 className="font-display text-3xl text-slate-900 dark:text-white">Profile unavailable</h1><p className="mt-2 text-sm text-slate-500">We could not load your account details.</p><Button className="mt-4" onClick={loadProfile}>Try again</Button></section>

  const extractedSkills = Array.isArray(currentResume?.extracted_skills) ? currentResume.extracted_skills : Array.isArray(currentResume?.skills_result) ? currentResume.skills_result : Array.isArray(currentResume?.parsed_skills) ? currentResume.parsed_skills : (Array.isArray(currentResume?.skills) ? currentResume.skills : [])
  const displayName = profile.full_name || profile.name || authUser?.name || 'Your profile'

  return <div className="mx-auto max-w-5xl space-y-7 pb-12">
    <header className="flex items-end justify-between border-b border-slate-200 pb-5 dark:border-slate-800">
      <div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-700 dark:text-indigo-300">Account</p><h1 className="mt-1 font-display text-4xl font-semibold text-slate-900 dark:text-slate-100">Your profile</h1><p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Manage your personal information, account security, and preferences.</p></div>
      <StatusBadge status={role}>{roleLabel(role)}</StatusBadge>
    </header>

    <section className="grid grid-cols-[240px_1fr] gap-8 rounded-2xl border border-slate-200 bg-white p-7 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <aside className="border-r border-slate-200 pr-7 dark:border-slate-800">
        <div className="flex h-24 w-24 items-center justify-center overflow-hidden rounded-full bg-indigo-100 text-3xl font-semibold text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">
          {(profile.avatar_url || authUser?.avatar_url) ? <img src={profile.avatar_url || authUser?.avatar_url} alt={`${displayName} profile`} className="h-full w-full object-cover" /> : displayName.slice(0, 1).toUpperCase()}
        </div>
        <h2 className="mt-4 text-lg font-semibold text-slate-900 dark:text-white">{displayName}</h2>
        <p className="mt-1 break-all text-sm text-slate-500 dark:text-slate-400">{profile.email || authUser?.email}</p>
        <label className="mt-4 inline-flex cursor-pointer items-center rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">
          {avatarUploading ? 'Uploading…' : 'Change photo'}<input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={handleAvatarChange} disabled={avatarUploading} />
        </label>
        <p className="mt-2 text-xs leading-5 text-slate-500">PNG, JPEG or WebP. Use a square image for best results.</p>
      </aside>

      <form onSubmit={handleSubmit} className="space-y-5">
        <div><h2 className="text-lg font-semibold text-slate-900 dark:text-white">Personal information</h2><p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Your profile information is used throughout TalentMatch.</p></div>
        <div className="grid grid-cols-2 gap-5">
          <Field label="Full name" value={form.full_name} onChange={set('full_name')} autoComplete="name" required />
          <Field label="Email address" value={profile.email || authUser?.email || ''} readOnly className="cursor-not-allowed bg-slate-50 dark:bg-slate-950" />
          <Field label="Phone" type="tel" value={form.phone} onChange={set('phone')} autoComplete="tel" />
          {isRecruiter && <Field label="Company" value={form.company} onChange={set('company')} autoComplete="organization" />}
          {isRecruiter && <Field label="Job title" value={form.title} onChange={set('title')} autoComplete="organization-title" />}
          {isCandidate && <Field label="Location" value={form.location} onChange={set('location')} autoComplete="address-level2" />}
          {isCandidate && <Field label="Desired role" value={form.desired_role} onChange={set('desired_role')} placeholder="e.g. Backend Engineer" />}
          {isCandidate && <Field label="Years of experience" type="number" min="0" max="80" value={form.experience_years} onChange={set('experience_years')} />}
          {isCandidate && <div className="col-span-2"><Field label="Skills" as="textarea" rows={3} value={form.skills} onChange={set('skills')} hint="Separate skills with commas." placeholder="Python, FastAPI, PostgreSQL" /></div>}
        </div>
        <div className="flex justify-end border-t border-slate-100 pt-4 dark:border-slate-800"><Button type="submit" disabled={saving}>{saving ? 'Saving changes…' : 'Save profile'}</Button></div>
      </form>
    </section>

    {isCandidate && <section className="rounded-2xl border border-slate-200 bg-white p-7 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-6"><div><h2 className="text-lg font-semibold text-slate-900 dark:text-white">Resume and extracted skills</h2><p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Keep your resume current to apply for roles and improve matching.</p></div><Button onClick={() => setResumeModalOpen(true)}>{currentResume ? 'Replace resume' : 'Upload resume'}</Button></div>
      {resumesLoading ? <div className="flex justify-center py-8"><Spinner label="Loading resume" /></div> : currentResume ? <div className="mt-5 grid grid-cols-[1fr_1fr] gap-6">
        <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700"><div className="flex items-start justify-between gap-3"><div><p className="break-all text-sm font-semibold text-slate-900 dark:text-slate-100">{currentResume.original_filename || currentResume.filename || 'Uploaded resume'}</p><p className="mt-1 text-xs text-slate-500">{currentResume.uploaded_at ? new Date(currentResume.uploaded_at).toLocaleDateString() : 'Resume on file'}</p></div><StatusBadge status={currentResume.skills_extraction_status || currentResume.extraction_status || currentResume.status}>{currentResume.skills_extraction_status || currentResume.extraction_status || currentResume.status || 'Uploaded'}</StatusBadge></div><div className="mt-4 flex gap-2"><Button variant="secondary" size="sm" onClick={() => setPreviewOpen((value) => !value)}>{previewOpen ? 'Hide preview' : 'Preview resume'}</Button><Button variant="danger" size="sm" onClick={() => setResumeToDelete(true)}>Delete resume</Button></div>{previewOpen && <ResumePreview resume={currentResume} />}</div>
        <div><p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Skills found in your resume</p>{extractedSkills.length ? <div className="mt-3 flex flex-wrap gap-2">{extractedSkills.map((item) => { const skill = typeof item === 'string' ? item : (item.name || item.skill || String(item)); return <span key={skill} className="rounded-full bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">{skill}</span> })}</div> : <p className="mt-2 text-sm text-slate-500">No extracted skills are available yet. They will appear here when resume processing is complete.</p>}</div>
      </div> : <div className="mt-5 rounded-xl border border-dashed border-indigo-300 bg-indigo-50/60 px-5 py-6 dark:border-indigo-900 dark:bg-indigo-950/30"><p className="text-sm font-semibold text-slate-900 dark:text-slate-100">Upload your resume to start applying</p><p className="mt-1 text-sm text-slate-600 dark:text-slate-300">TalentMatch uses your resume to help organize and process applications.</p><Button className="mt-4" onClick={() => setResumeModalOpen(true)}>Upload resume</Button></div>}
    </section>}

    <section className="rounded-2xl border border-slate-200 bg-white p-7 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-5"><h2 className="text-lg font-semibold text-slate-900 dark:text-white">Change password</h2><p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Use a strong password you do not reuse on other sites.</p></div>
      <form onSubmit={handleChangePassword} className="grid grid-cols-2 gap-5">
        <Field label="Current password" type="password" autoComplete="current-password" value={passwordForm.current} onChange={(event) => setPasswordForm((state) => ({ ...state, current: event.target.value }))} required />
        <div />
        <Field label="New password" type="password" autoComplete="new-password" value={passwordForm.next} onChange={(event) => setPasswordForm((state) => ({ ...state, next: event.target.value }))} hint="At least 8 characters, including uppercase, lowercase, and a number." required />
        <Field label="Confirm new password" type="password" autoComplete="new-password" value={passwordForm.confirm} onChange={(event) => setPasswordForm((state) => ({ ...state, confirm: event.target.value }))} required />
        <div className="col-span-2 flex justify-end"><Button type="submit" disabled={changingPassword || !passwordForm.current || !passwordForm.next || !passwordForm.confirm}>{changingPassword ? 'Updating…' : 'Update password'}</Button></div>
      </form>
    </section>

    {!isSuperuser && <section className="flex items-center justify-between rounded-2xl border border-red-200 bg-white p-7 dark:border-red-950 dark:bg-slate-900"><div><h2 className="text-lg font-semibold text-red-700 dark:text-red-400">Delete account</h2><p className="mt-1 max-w-2xl text-sm text-slate-500 dark:text-slate-400">Permanently delete your account and associated resumes and applications. This cannot be undone.</p></div><Button variant="danger" onClick={() => setDeleteAccountOpen(true)}>Delete account</Button></section>}

    <ResumeUploadModal open={resumeModalOpen} onClose={() => setResumeModalOpen(false)} currentResume={currentResume} onUploaded={() => { refetchResumes(); setResumeModalOpen(false) }} />
    <ConfirmDialog open={Boolean(resumeToDelete)} onClose={() => setResumeToDelete(false)} onConfirm={handleDeleteResume} title="Delete resume?" message="This will remove your current resume from TalentMatch." confirmLabel="Delete resume" destructive busy={deletingResume} />
    <Modal open={deleteAccountOpen} onClose={() => { if (!deletingAccount) { setDeleteAccountOpen(false); setDeletePassword(''); setDeleteText('') } }} title="Delete your account" footer={<><Button variant="secondary" onClick={() => { setDeleteAccountOpen(false); setDeletePassword(''); setDeleteText('') }} disabled={deletingAccount}>Cancel</Button><Button variant="danger" onClick={handleDeleteAccount} disabled={deletingAccount || !deletePassword || deleteText !== 'DELETE'}>{deletingAccount ? 'Deleting…' : 'Permanently delete'}</Button></>}>
      <div className="space-y-4"><p className="text-sm leading-6 text-slate-600 dark:text-slate-300">This action is permanent. Your resumes, related files, and applications will be removed. Confirm your password and type <strong>DELETE</strong> to continue.</p><Field label="Current password" type="password" autoComplete="current-password" value={deletePassword} onChange={(event) => setDeletePassword(event.target.value)} required /><Field label="Type DELETE to confirm" value={deleteText} onChange={(event) => setDeleteText(event.target.value)} autoComplete="off" required /></div>
    </Modal>
  </div>
}
