import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { changePassword, deleteMyAccount, fetchMe, updateMe, uploadAvatar } from '../api/users'
import { deleteResume, rerunResumeExtraction } from '../api/resumes'
import { useResumes } from '../hooks/useResumes'
import ResumeUploadModal from '../components/resume/ResumeUploadModal'
import ResumePreview from '../components/resume/ResumePreview'
import Spinner from '../components/ui/Spinner'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import { useToast } from '../components/ui/Toast'
import { formatEnumLabel, getErrorMessage } from '../utils/format'
import StatusBadge from '../components/ui/StatusBadge'
import Modal from '../components/ui/Modal'
import Button from '../components/ui/Button'
import Field from '../components/ui/Field'
import PageHeader from '../components/ui/PageHeader'
import ProfileFields from '../components/profile/ProfileFields'
import { ExtractionStatusBadge } from '../components/resume/ResumeExtractionModal'
import { toFormState, toPayload } from '../utils/profileForm'

// Mirrors the backend password rule (letter + number, 8+ chars); the server is the real gate.
function passwordProblem(value) {
  if (value.length < 8) return 'Use at least 8 characters.'
  if (!/[A-Za-z]/.test(value)) return 'Include at least one letter.'
  if (!/[0-9]/.test(value)) return 'Include at least one number.'
  return null
}

export default function Profile() {
  const { logout, refreshProfile } = useAuth()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(() => toFormState(null))
  const [saving, setSaving] = useState(false)
  const [avatarUploading, setAvatarUploading] = useState(false)
  const [resumeModalOpen, setResumeModalOpen] = useState(false)
  const [confirmDeleteResume, setConfirmDeleteResume] = useState(false)
  const [deletingResume, setDeletingResume] = useState(false)
  const [rerunning, setRerunning] = useState(false)
  const [pwForm, setPwForm] = useState({ current: '', next: '', confirm: '' })
  const [pwSaving, setPwSaving] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deletePassword, setDeletePassword] = useState('')
  const [deletingAccount, setDeletingAccount] = useState(false)
  const isCandidate = profile?.role === 'user'
  const { resumes, refetch: refetchResumes } = useResumes({ enabled: isCandidate })
  const currentResume = resumes[0]

  const handleDeleteResume = async () => {
    if (!currentResume) return
    setDeletingResume(true)
    try {
      await deleteResume(currentResume.id)
      showToast('Resume deleted.', 'success')
      refetchResumes()
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not delete your resume.'), 'error')
    } finally {
      setDeletingResume(false)
    }
  }

  const extractionStatus = String(currentResume?.skills_extraction_status ?? currentResume?.extraction_status ?? '').toLowerCase()
  const extractionInFlight = extractionStatus === 'pending' || extractionStatus === 'processing'

  const handleRerunExtraction = async () => {
    if (!currentResume) return
    setRerunning(true)
    try {
      await rerunResumeExtraction(currentResume.id)
      showToast('Extraction restarted.', 'success')
      refetchResumes()
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not restart extraction.'), 'error')
    } finally {
      setRerunning(false)
    }
  }

  // Quietly refresh while extraction is running so the badge flips to Done/Failed.
  // Gives up after ~3 minutes so a stuck job cannot keep the page polling forever.
  useEffect(() => {
    if (!extractionInFlight) return undefined
    let polls = 0
    const id = setInterval(() => {
      polls += 1
      if (polls > 45) { clearInterval(id); return }
      refetchResumes()
    }, 4000)
    return () => clearInterval(id)
  }, [extractionInFlight, refetchResumes])

  useEffect(() => {
    let mounted = true
    fetchMe()
      .then((data) => {
        if (!mounted) return
        setProfile(data)
        setForm(toFormState(data))
      })
      .catch(() => {
        if (mounted) showToast('Could not load your profile.', 'error')
      })
      .finally(() => mounted && setLoading(false))
    return () => { mounted = false }
  }, [showToast])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await updateMe(toPayload(form, profile?.role))
      setProfile(updated)
      setForm(toFormState(updated))
      // Keep the header (name, role, avatar) in step with what was just saved.
      refreshProfile().catch(() => {})
      showToast('Profile updated.', 'success')
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not update your profile.'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleAvatarChange = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setAvatarUploading(true)
    try {
      const updated = await uploadAvatar(file)
      setProfile(updated)
      refreshProfile().catch(() => {})
      showToast('Photo updated.', 'success')
    } catch (err) {
      const message =
        err.response?.status === 415 || err.response?.status === 413
          ? getErrorMessage(err, 'That image could not be uploaded.')
          : 'Could not upload the photo. Please try again.'
      showToast(message, 'error')
    } finally {
      setAvatarUploading(false)
      e.target.value = ''
    }
  }

  const pwError = pwForm.next ? passwordProblem(pwForm.next) : null
  const pwMismatch = pwForm.confirm && pwForm.next !== pwForm.confirm ? 'Passwords do not match.' : null
  const canChangePassword = pwForm.current && pwForm.next && pwForm.confirm && !pwError && !pwMismatch && !pwSaving

  const handleChangePassword = async (e) => {
    e.preventDefault()
    if (!canChangePassword) return
    setPwSaving(true)
    try {
      await changePassword(pwForm.current, pwForm.next)
      setPwForm({ current: '', next: '', confirm: '' })
      showToast('Password changed.', 'success')
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not change your password.'), 'error')
    } finally {
      setPwSaving(false)
    }
  }

  const closeDeleteAccount = () => { if (!deletingAccount) { setDeleteOpen(false); setDeletePassword('') } }
  const handleDeleteAccount = async () => {
    if (!deletePassword) return
    setDeletingAccount(true)
    try {
      await deleteMyAccount(deletePassword)
      await logout()
      navigate('/login', { replace: true })
    } catch (err) {
      // Includes the server's reasons: wrong password, still owns job postings, superuser.
      showToast(getErrorMessage(err, 'Could not delete your account.'), 'error')
      setDeletingAccount(false)
    }
  }

  if (loading) {
    return <div className="flex justify-center py-16"><Spinner size="lg" label="Loading profile" /></div>
  }

  return (
    <div className="mx-auto max-w-3xl px-8 py-8">
      <PageHeader
        eyebrow="Account"
        title="My profile"
        description="Keep your details current. Recruiters and administrators see this information when reviewing applications and access requests."
        meta={profile && <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400"><StatusBadge status={profile.role}>{formatEnumLabel(profile.role === 'user' ? 'applicant' : profile.role)}</StatusBadge><span>{profile.email}</span>{profile.sub_company && <span>· {profile.sub_company}</span>}</div>}
      />

      <section className="mb-6 rounded-2xl border border-slate-200/80 bg-[#fbfaf7]/95 p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/90">
        <h2 className="font-display mb-4 text-2xl font-semibold text-slate-900 dark:text-slate-100">Photo</h2>
        <div className="flex items-center gap-4">
          <div className="h-16 w-16 shrink-0 overflow-hidden rounded-full bg-slate-100 ring-1 ring-slate-200 dark:bg-slate-800 dark:ring-slate-700">
            {profile?.avatar_url
              ? <img src={profile.avatar_url} alt="Your avatar" className="h-full w-full object-cover" />
              : <span aria-hidden="true" className="flex h-full w-full items-center justify-center bg-indigo-100 text-lg font-semibold text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">{(profile?.full_name || profile?.email || '?').split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase()}</span>}
          </div>
          <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-slate-200 bg-[#fbfaf7] px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-indigo-200 hover:bg-white hover:text-indigo-700 focus-within:ring-2 focus-within:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800">
            {avatarUploading ? <Spinner size="sm" label="Uploading" /> : profile?.avatar_url ? 'Replace photo' : 'Upload photo'}
            <input type="file" accept="image/jpeg,image/png,image/webp" onChange={handleAvatarChange} disabled={avatarUploading} className="sr-only" />
          </label>
          <p className="text-xs text-slate-500 dark:text-slate-400">JPEG, PNG or WebP.</p>
        </div>
      </section>
    

      <section className="mb-6 rounded-2xl border border-slate-200/80 bg-[#fbfaf7]/95 p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/90">
        <h2 className="font-display mb-4 text-2xl font-semibold text-slate-900 dark:text-slate-100">Personal information</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <ProfileFields role={profile?.role} form={form} onChange={setForm} />

          <Button type="submit" disabled={saving}>
            {saving ? <Spinner size="sm" label="Saving" /> : 'Save changes'}
          </Button>
        </form>
      </section>

      {isCandidate && (
        <section className="rounded-2xl border border-slate-200/80 bg-[#fbfaf7]/95 p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/90">
          <h2 className="font-display mb-4 text-2xl font-semibold text-slate-900 dark:text-slate-100">Resume</h2>
          {currentResume ? (
            <p className="mb-3 flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
              On file: {currentResume.original_filename}
              <StatusBadge status={currentResume.status}>{formatEnumLabel(currentResume.status)}</StatusBadge>
            </p>
          ) : (
            <p className="mb-3 text-sm text-slate-400 dark:text-slate-500">No resume uploaded yet.</p>
          )}
          {currentResume && (
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
              Skills extraction: <ExtractionStatusBadge status={extractionStatus} />
              {!extractionInFlight && (
                <button type="button" onClick={handleRerunExtraction} disabled={rerunning} className="font-medium text-slate-700 underline hover:no-underline disabled:opacity-50 dark:text-slate-300">
                  {rerunning ? 'Restarting…' : 'Re-run extraction'}
                </button>
              )}
            </div>
          )}
          <div className="flex items-center gap-2">
            <Button onClick={() => setResumeModalOpen(true)}>
              {currentResume ? 'Replace resume' : 'Upload resume'}
            </Button>
            {currentResume && (
              <Button variant="subtle" onClick={() => setConfirmDeleteResume(true)} disabled={deletingResume} className="!text-red-600 hover:!bg-red-50 dark:!text-red-400 dark:hover:!bg-red-950/50">
                {deletingResume ? <Spinner size="sm" label="Deleting" /> : 'Delete resume'}
              </Button>
            )}
          </div>
          {currentResume && <ResumePreview resume={currentResume} />}
          <ResumeUploadModal open={resumeModalOpen} onClose={() => setResumeModalOpen(false)} currentResume={currentResume} onUploaded={refetchResumes} />
          <ConfirmDialog
            open={confirmDeleteResume}
            onClose={() => setConfirmDeleteResume(false)}
            onConfirm={handleDeleteResume}
            title="Delete your resume?"
            message="You won't be able to apply to jobs until you upload a new one."
            confirmLabel="Delete"
            destructive
          />
        </section>
      )}

      <section id="security" className="mt-6 rounded-2xl border border-slate-200/80 bg-[#fbfaf7]/95 p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/90">
        <h2 className="font-display mb-4 text-2xl font-semibold text-slate-900 dark:text-slate-100">Change password</h2>
        <form onSubmit={handleChangePassword} className="max-w-sm space-y-3">
          <Field label="Current password" type="password" autoComplete="current-password" value={pwForm.current} onChange={(e) => setPwForm((f) => ({ ...f, current: e.target.value }))} />
          <Field label="New password" type="password" autoComplete="new-password" hint="At least 8 characters, with a letter and a number." error={pwError} value={pwForm.next} onChange={(e) => setPwForm((f) => ({ ...f, next: e.target.value }))} />
          <Field label="Confirm new password" type="password" autoComplete="new-password" error={pwMismatch} value={pwForm.confirm} onChange={(e) => setPwForm((f) => ({ ...f, confirm: e.target.value }))} />
          <Button type="submit" disabled={!canChangePassword}>{pwSaving ? 'Saving…' : 'Change password'}</Button>
        </form>
      </section>

      <section className="mt-6 rounded-2xl border border-red-200/80 bg-red-50/40 p-6 dark:border-red-900/70 dark:bg-red-950/20">
        <h2 className="font-display mb-1 text-2xl font-semibold text-red-800 dark:text-red-300">Delete account</h2>
        {profile?.role === 'superuser' ? (
          <p className="text-xs text-slate-500 dark:text-slate-400">The superuser account can't be deleted. Transfer superuser status to another account first.</p>
        ) : (
          <>
            <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
              Permanently removes your account{isCandidate ? ', your resume and your applications' : ' and the resumes you uploaded'}. If you still own job postings, an admin has to reassign or close them first.
            </p>
            <Button variant="danger" onClick={() => setDeleteOpen(true)}>Delete my account</Button>
          </>
        )}
      </section>

      <Modal
        open={deleteOpen}
        onClose={closeDeleteAccount}
        title="Delete your account?"
        size="md"
        footer={<>
          <Button variant="secondary" onClick={closeDeleteAccount} disabled={deletingAccount}>Cancel</Button>
          <Button variant="danger" onClick={handleDeleteAccount} disabled={!deletePassword || deletingAccount}>{deletingAccount ? 'Deleting…' : 'Delete account'}</Button>
        </>}
      >
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">This can't be undone. Enter your password to confirm.</p>
        <Field label="Password" type="password" autoComplete="current-password" value={deletePassword} onChange={(e) => setDeletePassword(e.target.value)} />
      </Modal>
    </div>
  )
}
