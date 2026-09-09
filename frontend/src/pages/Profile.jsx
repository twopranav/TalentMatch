import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { fetchMe, updateMe, uploadAvatar } from '../api/users'
import { useResumes } from '../hooks/useResumes'
import ResumeUploadModal from '../components/resume/ResumeUploadModal'
import ResumePreview from '../components/resume/ResumePreview'
import Spinner from '../components/ui/Spinner'
import { useToast } from '../components/ui/Toast'
import { getErrorMessage } from '../utils/format'

const LABEL_CLASSES = 'mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400'
const INPUT_CLASSES = 'w-full rounded border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100'

function emptyFormFor(role) {
  return {
    full_name: '', phone: '', company: '', title: '', skills: '',
    experience_years: '', location: '', desired_role: '',
  }
}

function toFormState(user) {
  return {
    full_name: user.full_name || '',
    phone: user.phone || '',
    company: user.company || '',
    title: user.title || '',
    skills: Array.isArray(user.skills) ? user.skills.join(', ') : '',
    experience_years: user.experience_years ?? '',
    location: user.location || '',
    desired_role: user.desired_role || '',
  }
}

function toPayload(form) {
  const payload = { ...form }
  payload.skills = payload.skills
    ? payload.skills.split(',').map((s) => s.trim()).filter(Boolean)
    : []
  payload.experience_years = payload.experience_years === '' ? null : Number(payload.experience_years)
  return payload
}

export default function Profile() {
  const { user: authUser } = useAuth()
  const { showToast } = useToast()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(emptyFormFor(authUser?.role))
  const [saving, setSaving] = useState(false)
  const [avatarUploading, setAvatarUploading] = useState(false)
  const [resumeModalOpen, setResumeModalOpen] = useState(false)
  const isCandidate = profile?.role === 'user'
  const { resumes, refetch: refetchResumes } = useResumes({ enabled: isCandidate })
  const currentResume = resumes[0]

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

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await updateMe(toPayload(form))
      setProfile(updated)
      setForm(toFormState(updated))
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

  if (loading) {
    return <div className="flex justify-center py-16"><Spinner size="lg" label="Loading profile" /></div>
  }

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="mb-6 text-xl font-semibold text-slate-800 dark:text-slate-100">My Profile</h1>

      {isCandidate && (
        <section className="mb-6 rounded border border-slate-200 p-4 dark:border-slate-700">
          <h2 className="mb-3 text-sm font-medium text-slate-700 dark:text-slate-300">Photo</h2>
          <div className="flex items-center gap-4">
            <div className="h-16 w-16 shrink-0 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              {profile?.avatar_url && <img src={profile.avatar_url} alt="Your avatar" className="h-full w-full object-cover" />}
            </div>
            <label className="cursor-pointer rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600">
              {avatarUploading ? <Spinner size="sm" label="Uploading" /> : profile?.avatar_url ? 'Replace photo' : 'Upload photo'}
              <input type="file" accept="image/jpeg,image/png,image/webp" onChange={handleAvatarChange} disabled={avatarUploading} className="hidden" />
            </label>
          </div>
        </section>
      )}

      <section className="mb-6 rounded border border-slate-200 p-4 dark:border-slate-700">
        <h2 className="mb-3 text-sm font-medium text-slate-700 dark:text-slate-300">Personal information</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div><label className={LABEL_CLASSES}>Full name</label><input value={form.full_name} onChange={set('full_name')} className={INPUT_CLASSES} /></div>
            <div><label className={LABEL_CLASSES}>Phone</label><input value={form.phone} onChange={set('phone')} className={INPUT_CLASSES} /></div>
          </div>

          {profile?.role === 'recruiter' ? (
            <div className="grid grid-cols-2 gap-3">
              <div><label className={LABEL_CLASSES}>Company</label><input value={form.company} onChange={set('company')} className={INPUT_CLASSES} /></div>
              <div><label className={LABEL_CLASSES}>Title</label><input value={form.title} onChange={set('title')} className={INPUT_CLASSES} /></div>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div><label className={LABEL_CLASSES}>Location</label><input value={form.location} onChange={set('location')} className={INPUT_CLASSES} /></div>
                <div><label className={LABEL_CLASSES}>Years of experience</label><input type="number" min="0" value={form.experience_years} onChange={set('experience_years')} className={INPUT_CLASSES} /></div>
              </div>
              <div><label className={LABEL_CLASSES}>Desired role</label><input value={form.desired_role} onChange={set('desired_role')} className={INPUT_CLASSES} /></div>
              <div><label className={LABEL_CLASSES}>Skills (comma-separated)</label><input value={form.skills} onChange={set('skills')} placeholder="React, SQL, Python" className={INPUT_CLASSES} /></div>
            </>
          )}

          <button type="submit" disabled={saving} className="flex items-center gap-2 rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600">
            {saving ? <Spinner size="sm" label="Saving" /> : 'Save changes'}
          </button>
        </form>
      </section>

      {isCandidate && (
        <section className="rounded border border-slate-200 p-4 dark:border-slate-700">
          <h2 className="mb-3 text-sm font-medium text-slate-700 dark:text-slate-300">Resume</h2>
          {currentResume ? <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">On file: {currentResume.original_filename}</p> : <p className="mb-3 text-sm text-slate-400 dark:text-slate-500">No resume uploaded yet.</p>}
          <button onClick={() => setResumeModalOpen(true)} className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 dark:bg-slate-700 dark:hover:bg-slate-600">
            {currentResume ? 'Replace resume' : 'Upload resume'}
          </button>
          {currentResume && <ResumePreview resume={currentResume} />}
          <ResumeUploadModal open={resumeModalOpen} onClose={() => setResumeModalOpen(false)} currentResume={currentResume} onUploaded={refetchResumes} />
        </section>
      )}
    </div>
  )
}