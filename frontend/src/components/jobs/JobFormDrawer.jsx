import { formatEnumLabel } from '../../utils/format'
import { useEffect, useState } from 'react'
import Modal from '../ui/Modal'
import Spinner from '../ui/Spinner'
import { createJob, updateJob } from '../../api/jobs'
import { useToast } from '../ui/Toast'

const EMPLOYMENT_TYPES = ['full_time', 'part_time', 'contract', 'internship']
const SENIORITY_LEVELS = ['entry', 'mid', 'senior', 'lead', 'executive']
const REMOTE_TYPES = ['onsite', 'remote', 'hybrid']

const EMPTY_FORM = {
  title: '',
  description: '',
  location: '',
  employment_type: 'full_time',
  department: '',
  seniority: '',
  remote_type: '',
  salary_min: '',
  salary_max: '',
  min_experience_years: '',
  max_experience_years: '',
  education_requirement: '',
}

const INPUT_CLASSES =
  'w-full rounded border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500'
const LABEL_CLASSES = 'mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300'

function toFormState(job) {
  if (!job) return EMPTY_FORM
  return {
    title: job.title || '',
    description: job.description || '',
    location: job.location || '',
    employment_type: job.employment_type || 'full_time',
    department: job.department || '',
    seniority: job.seniority || '',
    remote_type: job.remote_type || '',
    salary_min: job.salary_min ?? '',
    salary_max: job.salary_max ?? '',
    min_experience_years: job.min_experience_years ?? '',
    max_experience_years: job.max_experience_years ?? '',
    education_requirement: job.education_requirement || '',
  }
}

function toPayload(form) {
  const payload = { ...form }
  for (const key of ['seniority', 'remote_type', 'department', 'location', 'description', 'education_requirement']) {
    if (payload[key] === '') payload[key] = null
  }
  for (const key of ['salary_min', 'salary_max', 'min_experience_years', 'max_experience_years']) {
    payload[key] = payload[key] === '' ? null : Number(payload[key])
  }
  return payload
}

export default function JobFormDrawer({ open, onClose, job, onSaved }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const { showToast } = useToast()
  const isEdit = Boolean(job)

  useEffect(() => {
    if (open) setForm(toFormState(job))
  }, [open, job])

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const payload = toPayload(form)
      const saved = isEdit ? await updateJob(job.id, payload) : await createJob(payload)
      showToast(isEdit ? 'Job updated.' : 'Job created as draft.', 'success')
      onSaved(saved)
      onClose()
    } catch (err) {
      showToast('Could not save the job. Please check the fields and try again.', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEdit ? 'Edit job' : 'New job'}
      footer={
        <>
          <button onClick={onClose} className="rounded px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="flex items-center gap-2 rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600"
          >
            {submitting ? <Spinner size="sm" label="Saving" /> : isEdit ? 'Save changes' : 'Create draft'}
          </button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className={LABEL_CLASSES}>Title</label>
          <input required value={form.title} onChange={set('title')} className={INPUT_CLASSES} />
        </div>

        <div>
          <label className={LABEL_CLASSES}>Description</label>
          <textarea value={form.description} onChange={set('description')} rows={3} className={INPUT_CLASSES} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={LABEL_CLASSES}>Location</label>
            <input value={form.location} onChange={set('location')} className={INPUT_CLASSES} />
          </div>
          <div>
            <label className={LABEL_CLASSES}>Department</label>
            <input value={form.department} onChange={set('department')} className={INPUT_CLASSES} />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className={LABEL_CLASSES}>Employment type</label>
            <select value={form.employment_type} onChange={set('employment_type')} className={INPUT_CLASSES}>
              {EMPLOYMENT_TYPES.map((v) => (
                <option key={v} value={v}>{formatEnumLabel(v)}</option>
               ))}
            </select>
          </div>
          <div>
            <label className={LABEL_CLASSES}>Seniority</label>
            <select value={form.seniority} onChange={set('seniority')} className={INPUT_CLASSES}>
              <option value="">—</option>
              {SENIORITY_LEVELS.map((v) => (
                <option key={v} value={v}>{formatEnumLabel(v)}</option>
               ))}
            </select>
          </div>
          <div>
            <label className={LABEL_CLASSES}>Remote</label>
            <select value={form.remote_type} onChange={set('remote_type')} className={INPUT_CLASSES}>
              <option value="">—</option>
              {REMOTE_TYPES.map((v) => (
                <option key={v} value={v}>{formatEnumLabel(v)}</option>
               ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={LABEL_CLASSES}>Salary min</label>
            <input type="number" value={form.salary_min} onChange={set('salary_min')} className={INPUT_CLASSES} />
          </div>
          <div>
            <label className={LABEL_CLASSES}>Salary max</label>
            <input type="number" value={form.salary_max} onChange={set('salary_max')} className={INPUT_CLASSES} />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={LABEL_CLASSES}>Min experience (yrs)</label>
            <input type="number" value={form.min_experience_years} onChange={set('min_experience_years')} className={INPUT_CLASSES} />
          </div>
          <div>
            <label className={LABEL_CLASSES}>Max experience (yrs)</label>
            <input type="number" value={form.max_experience_years} onChange={set('max_experience_years')} className={INPUT_CLASSES} />
          </div>
        </div>

        <div>
          <label className={LABEL_CLASSES}>Education requirement</label>
          <input value={form.education_requirement} onChange={set('education_requirement')} className={INPUT_CLASSES} />
        </div>
      </form>
    </Modal>
  )
}