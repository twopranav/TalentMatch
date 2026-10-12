import { useCallback, useEffect, useState } from 'react'
import Spinner from '../ui/Spinner'
import { useToast } from '../ui/Toast'
import { fetchAllResumes } from '../../api/resumes'
import { bulkApplyResumes, fetchJobApplications } from '../../api/applications'
import { getErrorMessage } from '../../utils/format'
import { ExtractionStatusBadge } from '../resume/ResumeExtractionModal'

function extractionState(resume) {
  return String(resume.skills_extraction_status ?? resume.extraction_status ?? '').toLowerCase()
}

// Applies resumes from the library (bulk-uploaded, no candidate account) to
// this job as recruiter-submitted applications. Only rendered for
// recruiter / superuser on a published job (see JobApplicants.jsx).
// The server decides what each role can use: a recruiter's list is just
// their own uploads, a superuser's is everything unowned.
export default function BulkApplyPanel({ job, onApplied }) {
  const { showToast } = useToast()
  const [open, setOpen] = useState(false)
  const [resumes, setResumes] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(() => new Set())
  const [submitting, setSubmitting] = useState(false)
  const [results, setResults] = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    Promise.all([fetchAllResumes(), fetchJobApplications(job.id)])
      .then(([all, applicants]) => {
        const alreadyApplied = new Set(applicants.map((a) => a.resume_id).filter(Boolean))
        setResumes(
          all.filter(
            (r) =>
              !r.owner_id &&
              !r.is_archived &&
              extractionState(r) !== 'failed' &&
              !alreadyApplied.has(r.id),
          ),
        )
        setSelected(new Set())
      })
      .catch((err) => setError(getErrorMessage(err, 'Could not load your resumes.')))
      .finally(() => setLoading(false))
  }, [job.id])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  const allSelected = resumes.length > 0 && selected.size === resumes.length

  const toggleOne = (id) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(resumes.map((r) => r.id)))

  const handleApply = async () => {
    if (selected.size === 0) return
    setSubmitting(true)
    setResults(null)
    try {
      const outcome = await bulkApplyResumes(job.id, [...selected])
      setResults(outcome)
      const ok = outcome.filter((r) => r.success).length
      const failed = outcome.length - ok
      showToast(
        failed === 0
          ? `${ok} resume${ok === 1 ? '' : 's'} added as applicants.`
          : `${ok} added, ${failed} failed.`,
        failed === 0 ? 'success' : 'error',
      )
      load()
      if (ok > 0 && onApplied) onApplied()
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not apply those resumes.'), 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mb-6 rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Add resumes from library</h2>
        <button
          onClick={() => setOpen((v) => !v)}
          className="text-xs font-medium text-slate-700 underline hover:no-underline dark:text-slate-300"
        >
          {open ? 'Hide' : 'Choose resumes'}
        </button>
      </div>

      {open && (
        <div className="mt-3">
          <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
            Resumes without a candidate account that aren't on this job yet. Each one becomes an applicant and is
            scored against the job's required skills. Resumes still being read are fine; they score once ready.
          </p>

          {loading ? (
            <div className="flex justify-center py-4"><Spinner size="sm" label="Loading resumes" /></div>
          ) : error ? (
            <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
          ) : resumes.length === 0 ? (
            <p className="text-xs text-slate-400 dark:text-slate-500">
              No resumes available to add. Upload some on the Resume Library page.
            </p>
          ) : (
            <>
              <div className="max-h-72 overflow-y-auto rounded border border-slate-100 dark:border-slate-700">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
                    <tr>
                      <th className="w-8 px-3 py-2">
                        <input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label="Select all resumes" />
                      </th>
                      <th className="px-3 py-2 font-medium">File</th>
                      <th className="px-3 py-2 font-medium">Candidate</th>
                      <th className="px-3 py-2 font-medium">Uploaded by</th>
                      <th className="px-3 py-2 font-medium">Extraction</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resumes.map((r) => (
                      <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                        <td className="px-3 py-2">
                          <input
                            type="checkbox"
                            checked={selected.has(r.id)}
                            onChange={() => toggleOne(r.id)}
                            aria-label={`Select ${r.original_filename}`}
                          />
                        </td>
                        <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{r.original_filename}</td>
                        <td className="px-3 py-2 text-slate-600 dark:text-slate-400">
                          {r.candidate_name || r.candidate_email || 'Unclaimed'}
                        </td>
                        <td className="px-3 py-2 text-slate-500 dark:text-slate-400">{r.uploaded_by_email || '—'}</td>
                        <td className="px-3 py-2">
                          <ExtractionStatusBadge status={r.skills_extraction_status ?? r.extraction_status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-3 flex items-center gap-3">
                <button
                  onClick={handleApply}
                  disabled={selected.size === 0 || submitting}
                  className="flex items-center gap-2 rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600"
                >
                  {submitting ? (
                    <Spinner size="sm" label="Applying" />
                  ) : (
                    `Add ${selected.size || ''} applicant${selected.size === 1 ? '' : 's'}`
                  )}
                </button>
                <span className="text-xs text-slate-400 dark:text-slate-500">
                  {selected.size} of {resumes.length} selected
                </span>
              </div>
            </>
          )}

          {results && (
            <ul className="mt-4 space-y-1 text-xs">
              {results.map((r, i) => (
                <li key={i} className={r.success ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}>
                  {r.success ? '✓' : '✗'} {r.original_filename}{!r.success && r.error ? ` — ${r.error}` : ''}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}