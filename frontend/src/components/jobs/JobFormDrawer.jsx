import { formatEnumLabel, getErrorMessage } from '../../utils/format'
import { useEffect, useState } from 'react'
import Modal from '../ui/Modal'
import Spinner from '../ui/Spinner'
import Button from '../ui/Button'
import Field from '../ui/Field'
import { createJob, updateJob } from '../../api/jobs'
import { useToast } from '../ui/Toast'
import { useAuth } from '../../context/AuthContext'
import { SUB_COMPANIES } from '../../utils/subCompany'

const EMPLOYMENT_TYPES = ['full_time', 'part_time', 'contract', 'internship']
const SENIORITY_LEVELS = ['entry', 'mid', 'senior', 'lead', 'executive']
const REMOTE_TYPES = ['onsite', 'remote', 'hybrid']

const EMPTY_FORM = {
  title: '',
  description: '',
  location: '',
  employment_type: 'full_time',
  sub_company: '',
  department: '',
  seniority: '',
  remote_type: '',
  salary_min: '',
  salary_max: '',
  min_experience_years: '',
  max_experience_years: '',
  education_requirement: '',
}

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

// Catches the obvious range mistakes before a round trip to the server.
function validate(form) {
  const errors = {}
  const num = (value) => (value === '' ? null : Number(value))
  const [smin, smax, emin, emax] = [num(form.salary_min), num(form.salary_max), num(form.min_experience_years), num(form.max_experience_years)]
  if (smin != null && smax != null && smin > smax) errors.salary_max = 'Maximum salary must be at least the minimum.'
  if (emin != null && emax != null && emin > emax) errors.max_experience_years = 'Maximum experience must be at least the minimum.'
  for (const [key, value] of [['salary_min', smin], ['salary_max', smax], ['min_experience_years', emin], ['max_experience_years', emax]]) {
    if (value != null && value < 0) errors[key] = 'Cannot be negative.'
  }
  return errors
}

export default function JobFormDrawer({ open, onClose, job, onSaved }) {
  const { user } = useAuth()
  const [form, setForm] = useState(EMPTY_FORM)
  const [submitting, setSubmitting] = useState(false)
  const { showToast } = useToast()
  const isEdit = Boolean(job)
  const errors = validate(form)
  const hasErrors = Object.keys(errors).length > 0

  useEffect(() => {
    if (open) setForm(toFormState(job))
  }, [open, job])

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (hasErrors || submitting) return
    setSubmitting(true)
    try {
      const payload = toPayload(form)
      if (isEdit || !payload.sub_company) delete payload.sub_company
      const saved = isEdit ? await updateJob(job.id, payload) : await createJob(payload)
      showToast(isEdit ? 'Job updated.' : 'Job created as draft.', 'success')
      onSaved(saved)
      onClose()
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not save the job. Please check the fields and try again.'), 'error')
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
          <Button variant="secondary" onClick={onClose} disabled={submitting}>Cancel</Button>
          <Button type="submit" form="job-form" disabled={submitting || hasErrors}>
            {submitting ? <Spinner size="sm" label="Saving" /> : isEdit ? 'Save changes' : 'Create draft'}
          </Button>
        </>
      }
    >
      <form id="job-form" onSubmit={handleSubmit} className="space-y-4">
        <Field label="Title" required value={form.title} onChange={set('title')} placeholder="e.g. Senior Process Engineer" />
        <Field label="Description" as="textarea" rows={3} value={form.description} onChange={set('description')} hint="A short summary. Upload a full job description file afterwards so candidates can be matched." />

        <div className="grid grid-cols-2 gap-4">
          <Field label="Location" value={form.location} onChange={set('location')} />
          <Field label="Department" value={form.department} onChange={set('department')} />
        </div>

        {user?.role === 'superuser' && !isEdit && (
          <Field label="Sub company" as="select" required value={form.sub_company} onChange={set('sub_company')}>
            <option value="">Select…</option>
            {SUB_COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </Field>
        )}

        <div className="grid grid-cols-3 gap-4">
          <Field label="Employment type" as="select" value={form.employment_type} onChange={set('employment_type')}>
            {EMPLOYMENT_TYPES.map((v) => <option key={v} value={v}>{formatEnumLabel(v)}</option>)}
          </Field>
          <Field label="Seniority" as="select" value={form.seniority} onChange={set('seniority')}>
            <option value="">—</option>
            {SENIORITY_LEVELS.map((v) => <option key={v} value={v}>{formatEnumLabel(v)}</option>)}
          </Field>
          <Field label="Remote" as="select" value={form.remote_type} onChange={set('remote_type')}>
            <option value="">—</option>
            {REMOTE_TYPES.map((v) => <option key={v} value={v}>{formatEnumLabel(v)}</option>)}
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Salary min" type="number" min="0" value={form.salary_min} onChange={set('salary_min')} error={errors.salary_min} />
          <Field label="Salary max" type="number" min="0" value={form.salary_max} onChange={set('salary_max')} error={errors.salary_max} />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Min experience (yrs)" type="number" min="0" value={form.min_experience_years} onChange={set('min_experience_years')} error={errors.min_experience_years} />
          <Field label="Max experience (yrs)" type="number" min="0" value={form.max_experience_years} onChange={set('max_experience_years')} error={errors.max_experience_years} />
        </div>

        <Field label="Education requirement" value={form.education_requirement} onChange={set('education_requirement')} />
      </form>
    </Modal>
  )
}
