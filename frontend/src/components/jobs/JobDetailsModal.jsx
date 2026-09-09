import { useState } from 'react'
import Modal from '../ui/Modal'
import ConfirmDialog from '../ui/ConfirmDialog'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../ui/Toast'
import { updateJob, deleteJob } from '../../api/jobs'
import ApplicantsPanel from './ApplicantsPanel'
import { formatEnumLabel } from '../../utils/format'


const STATUS_STYLES = {
  draft: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  published: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  closed: 'bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-500',
}

const APPLICATION_STATUS_STYLES = {
  applied: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  under_review: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  shortlisted: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  rejected: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  hired: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
}

function formatLabel(value) {
  return value ? formatEnumLabel(value) : '—'
}

export default function JobDetailsModal({ open, onClose, job, onEdit, onUploadJD, onChanged, onDeleted, myApplication, onApplicationChanged }) {
  const { user } = useAuth()
  const { showToast } = useToast()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [busy, setBusy] = useState(false)

  const isPrivileged = user?.role === 'admin' || user?.role === 'superuser'
  const isOwner = Boolean(job) && job.created_by_id === user?.id
  const canManage = isPrivileged || isOwner
  const isApplicant = user?.role === 'user'

  if (!job) return null

  const setStatus = async (status) => {
    setBusy(true)
    try {
      const updated = await updateJob(job.id, { status })
      showToast(`Job marked ${formatEnumLabel(status).toLowerCase()}.`, 'success')
      onChanged(updated)
    } catch (err) {
      showToast('Could not update the job status.', 'error')
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async () => {
    setBusy(true)
    try {
      await deleteJob(job.id)
      showToast('Job deleted.', 'success')
      onDeleted(job.id)
      onClose()
    } catch (err) {
      showToast('Could not delete the job.', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={job.title}
        footer={
          canManage ? (
            <>
              <button onClick={() => setConfirmDelete(true)} disabled={busy} className="rounded px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950">
                Delete
              </button>
              <button onClick={() => onUploadJD(job)} disabled={busy} className="rounded px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
                Upload JD
              </button>
              {job.status === 'draft' && (
                <button onClick={() => setStatus('published')} disabled={busy} className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60">
                  Publish
                </button>
              )}
              {job.status === 'published' && (
                <button onClick={() => setStatus('closed')} disabled={busy} className="rounded bg-slate-600 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60">
                  Close
                </button>
              )}
              <button onClick={() => onEdit(job)} disabled={busy} className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600">
                Edit
              </button>
            </>
          ) : null
          // Applicants already have Apply/Withdraw on the job row in JobList —
          // this modal is opened from the "Metadata" button and is meant to be
          // a read-only details view, so it doesn't duplicate those actions.
          // The applicant's current status is still shown as a badge below.
        }
      >
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[job.status]}`}>
              {formatEnumLabel(job.status)}
            </span>
            {isApplicant && myApplication && (
              <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${APPLICATION_STATUS_STYLES[myApplication.status]}`}>
                Your application: {formatEnumLabel(myApplication.status)}
              </span>
            )}
          </div>

          {job.description && <p className="text-slate-600 dark:text-slate-300">{job.description}</p>}

          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-slate-600 dark:text-slate-300">
            <div><dt className="text-xs text-slate-400 dark:text-slate-500">Location</dt><dd>{formatLabel(job.location)}</dd></div>
            <div><dt className="text-xs text-slate-400 dark:text-slate-500">Department</dt><dd>{formatLabel(job.department)}</dd></div>
            <div><dt className="text-xs text-slate-400 dark:text-slate-500">Employment type</dt><dd>{formatLabel(job.employment_type)}</dd></div>
            <div><dt className="text-xs text-slate-400 dark:text-slate-500">Seniority</dt><dd>{formatLabel(job.seniority)}</dd></div>
            <div><dt className="text-xs text-slate-400 dark:text-slate-500">Remote</dt><dd>{formatLabel(job.remote_type)}</dd></div>
            <div>
              <dt className="text-xs text-slate-400 dark:text-slate-500">Salary</dt>
              <dd>{job.salary_min || job.salary_max ? `${job.salary_min ?? '—'} – ${job.salary_max ?? '—'}` : '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-400 dark:text-slate-500">Experience</dt>
              <dd>{job.min_experience_years || job.max_experience_years ? `${job.min_experience_years ?? '0'}–${job.max_experience_years ?? '+'} yrs` : '—'}</dd>
            </div>
            <div><dt className="text-xs text-slate-400 dark:text-slate-500">Education</dt><dd>{formatLabel(job.education_requirement)}</dd></div>
          </dl>

          {job.jd_raw_text && (
            <div>
              <dt className="text-xs text-slate-400 dark:text-slate-500">Extracted JD text</dt>
              <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap rounded border border-slate-100 bg-slate-50 p-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                {job.jd_raw_text}
              </p>
            </div>
          )}

          {canManage && <ApplicantsPanel job={job} active={open && canManage} />}
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={handleDelete}
        title="Delete this job?"
        message={`"${job.title}" will be permanently removed. This can't be undone.`}
        confirmLabel="Delete"
        destructive
      />
    </>
  )
}