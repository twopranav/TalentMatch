import { useEffect, useState } from 'react'
import Modal from '../ui/Modal'
import ConfirmDialog from '../ui/ConfirmDialog'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../ui/Toast'
import { updateJob, deleteJob, fetchJob, reextractJobSkills } from '../../api/jobs'
import { formatEnumLabel, formatExperienceMonths, getErrorMessage } from '../../utils/format'
import { ExtractionStatusBadge } from '../resume/ResumeExtractionModal'


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

function Chips({ items }) {
  if (!items || items.length === 0) return <span className="text-slate-400 dark:text-slate-500">—</span>
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item, i) => (
        <span key={i} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-300">
          {item}
        </span>
      ))}
    </div>
  )
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

  // Follows the backend while extraction runs. Local to this modal so a
  // poll never refetches the whole job list (which would flash its spinner).
  const [live, setLive] = useState(null)
  useEffect(() => {
    setLive(null)
  }, [job])

  const view = (live && job && live.id === job.id ? live : job) ?? {}
  const skillsStatus = String(view.skills_extraction_status ?? '').toLowerCase()
  const inFlight = Boolean(view.jd_raw_text) && (skillsStatus === 'pending' || skillsStatus === 'processing')

  // Quiet 4s polling, capped at ~3 minutes -- same pattern as ResumeLibrary.
  useEffect(() => {
    if (!open || !job || !inFlight) return undefined
    let polls = 0
    const id = setInterval(() => {
      polls += 1
      if (polls > 45) {
        clearInterval(id)
        return
      }
      fetchJob(job.id).then(setLive).catch(() => {})
    }, 4000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, job?.id, inFlight])

  const experienceLabel =
    view.min_experience_months == null
      ? 'Not stated'
      : view.min_experience_months === 0
        ? 'Entry level (none required)'
        : formatExperienceMonths(view.min_experience_months)

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

  const handleRerun = async () => {
    setBusy(true)
    try {
      const updated = await reextractJobSkills(job.id)
      setLive(updated)
      showToast('Extraction re-queued.', 'success')
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not re-run extraction.'), 'error')
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
              <button
                onClick={() => window.open(`/jobs/${job.id}/applicants`, '_blank', 'noopener,noreferrer')}
                disabled={busy}
                className="rounded px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                Applicants
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

          {canManage && (
            <p className="text-xs text-slate-400 dark:text-slate-500">
              Applicants and their resumes open in a new tab via the "Applicants" button below.
            </p>
          )}

          {job.jd_raw_text && (
            <div className="space-y-3 rounded border border-slate-100 p-3 dark:border-slate-700">
              {!isApplicant && (
                <div className="flex flex-wrap items-center gap-2">
                  <dt className="text-xs text-slate-400 dark:text-slate-500">Extraction</dt>
                  <ExtractionStatusBadge status={skillsStatus} />
                  {view.skills_extracted_at && (
                    <span className="text-xs text-slate-400 dark:text-slate-500">
                      {new Date(view.skills_extracted_at).toLocaleString()}
                    </span>
                  )}
                  {canManage && !inFlight && (
                    <button
                      onClick={handleRerun}
                      disabled={busy}
                      className="ml-auto text-xs font-medium text-slate-700 underline hover:no-underline disabled:opacity-50 dark:text-slate-300"
                    >
                      Re-run extraction
                    </button>
                  )}
                </div>
              )}

              {!isApplicant && skillsStatus === 'pending' && (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Extraction is queued for this job description.
                </p>
              )}

              {!isApplicant && skillsStatus === 'processing' && (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Extraction is currently running for this job description.
                </p>
              )}

              {!isApplicant && skillsStatus === 'failed' && (
                <div className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
                  {view.skills_extraction_error || 'Extraction failed for an unknown reason.'}
                </div>
              )}

              {skillsStatus === 'done' && (
                <div>
                  <dt className="mb-1 text-xs text-slate-400 dark:text-slate-500">Required skills (extracted)</dt>
                  <dd><Chips items={view.skills_result} /></dd>
                  {!isApplicant && view.skills_section_heading && (
                    <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                      Found under "{view.skills_section_heading}"
                    </p>
                  )}
                </div>
              )}

              {/* Experience is computed before the skills step, so it can exist
                  even when skills extraction failed. */}
              {(skillsStatus === 'done' || view.min_experience_months != null) && (
                <div>
                  <dt className="text-xs text-slate-400 dark:text-slate-500">Experience required (extracted)</dt>
                  <dd className="text-slate-600 dark:text-slate-300">{experienceLabel}</dd>
                </div>
              )}

              <p className="text-xs text-slate-400 dark:text-slate-500">
                Extracted values are separate from the recruiter-edited fields above and never overwrite them.
              </p>
            </div>
          )}

          {job.jd_raw_text && (
            <div>
              <dt className="text-xs text-slate-400 dark:text-slate-500">Extracted JD text</dt>
              <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap rounded border border-slate-100 bg-slate-50 p-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                {job.jd_raw_text}
              </p>
            </div>
          )}
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