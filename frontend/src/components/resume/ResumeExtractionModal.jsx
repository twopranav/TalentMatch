// frontend/src/components/resume/ResumeExtractionModal.jsx
import Modal from '../ui/Modal'
import { formatEnumLabel } from '../../utils/format'

export const EXTRACTION_STATUS_STYLES = {
  pending: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  processing: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  done: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
}

export function ExtractionStatusBadge({ status }) {
  if (!status) return null
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${EXTRACTION_STATUS_STYLES[status] ?? EXTRACTION_STATUS_STYLES.pending}`}>
      {formatEnumLabel(status)}
    </span>
  )
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

function formatEducationEntry(edu) {
  const parts = [edu.degree, edu.institution, edu.year].filter(Boolean)
  return parts.length ? parts.join(' — ') : 'Unspecified'
}

// resume: a ResumeRead object (already has extraction_status, extracted_*
// fields, extracted_profile from the API — no separate fetch needed).
export default function ResumeExtractionModal({ open, onClose, resume }) {
  if (!resume) return null

  const status = resume.extraction_status
  const profile = resume.extracted_profile || {}

  return (
    <Modal open={open} onClose={onClose} title={`Extraction — ${resume.original_filename}`}>
      <div className="space-y-4 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <ExtractionStatusBadge status={status} />
          {resume.extracted_at && (
            <span className="text-xs text-slate-400 dark:text-slate-500">
              Extracted {new Date(resume.extracted_at).toLocaleString()}
            </span>
          )}
        </div>

        {status === 'pending' && (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            This resume hasn't been through the extraction pipeline yet.
          </p>
        )}

        {status === 'processing' && (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Extraction is currently running for this resume.
          </p>
        )}

        {status === 'failed' && (
          <div className="rounded border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
            {resume.extraction_error || 'Extraction failed for an unknown reason.'}
          </div>
        )}

        {status === 'done' && (
          <>
            <div>
              <dt className="mb-1 text-xs text-slate-400 dark:text-slate-500">Skills</dt>
              <dd><Chips items={resume.extracted_skills} /></dd>
            </div>

            <div>
              <dt className="text-xs text-slate-400 dark:text-slate-500">Experience</dt>
              <dd className="text-slate-600 dark:text-slate-300">
                {resume.extracted_experience_years != null ? `${resume.extracted_experience_years} years` : 'Not stated'}
              </dd>
            </div>

            <div>
              <dt className="mb-1 text-xs text-slate-400 dark:text-slate-500">Education</dt>
              {resume.extracted_education?.length ? (
                <ul className="space-y-1 text-slate-600 dark:text-slate-300">
                  {resume.extracted_education.map((edu, i) => (
                    <li key={i}>{formatEducationEntry(edu)}</li>
                  ))}
                </ul>
              ) : (
                <dd className="text-slate-400 dark:text-slate-500">—</dd>
              )}
            </div>

            <div>
              <dt className="mb-1 text-xs text-slate-400 dark:text-slate-500">Certifications</dt>
              <dd><Chips items={resume.extracted_certifications} /></dd>
            </div>

            {profile.work_history?.length > 0 && (
              <div>
                <dt className="mb-1 text-xs text-slate-400 dark:text-slate-500">Work history</dt>
                <ul className="space-y-1 text-slate-600 dark:text-slate-300">
                  {profile.work_history.map((w, i) => (
                    <li key={i}>
                      {[w.title, w.company].filter(Boolean).join(' at ') || 'Unspecified role'}
                      {(w.start_date || w.end_date) && (
                        <span className="text-slate-400 dark:text-slate-500">
                          {' '}({w.start_date || '?'} – {w.end_date || 'present'})
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {(resume.candidate_name || resume.candidate_email) && (
              <p className="text-xs text-slate-400 dark:text-slate-500">
                Contact info populated from extraction: {[resume.candidate_name, resume.candidate_email].filter(Boolean).join(' · ')}
              </p>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}