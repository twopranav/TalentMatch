import { Fragment, useEffect, useState } from 'react'
import Spinner from '../ui/Spinner'
import { useToast } from '../ui/Toast'
import { fetchJobApplications, rescoreJobApplications, updateApplicationStatus } from '../../api/applications'
import { formatEnumLabel, formatExperienceMonths } from '../../utils/format'
import { openResumeFile } from '../../api/resumes'

const APPLICATION_STATUS_OPTIONS = ['applied', 'under_review', 'shortlisted', 'rejected', 'hired']

// Applicants are returned best-match first by the server (sort=score). The
// score itself is computed asynchronously, so a row can be 'pending' for a
// few seconds after applying / after a JD change.
function ScoreBadge({ applicant }) {
  const { match_status: state, match_score: score, match_error: err } = applicant
  if (score == null) {
    if (state === 'failed') {
      return <span title={err || 'Could not be scored'} className="text-red-600 dark:text-red-400">Unavailable</span>
    }
    return <span className="text-slate-400 dark:text-slate-500">Scoring…</span>
  }
  const tone =
    score >= 70
      ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
      : score >= 40
        ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
        : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
  return (
    <span className={`inline-block rounded px-2 py-0.5 font-semibold ${tone}`} title={state === 'pending' ? 'Re-scoring…' : undefined}>
      {Math.round(score)}%
    </span>
  )
}

function MatchDetails({ details }) {
  if (!details) return null
  const matched = details.matched || []
  const missing = details.missing || []
  const have = formatExperienceMonths(details.resume_months)
  const need = formatExperienceMonths(details.jd_min_months)
  return (
    <div className="space-y-2 text-xs text-slate-600 dark:text-slate-300">
      <div>
        <span className="mr-2 text-slate-400 dark:text-slate-500">Matched</span>
        {matched.length === 0 ? '—' : matched.map((m) => (
          <span key={m.jd_skill} title={`${Math.round(m.similarity * 100)}% similar`} className="mr-1 inline-block rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">
            {m.jd_skill}{m.resume_skill && m.resume_skill !== m.jd_skill ? ` ← ${m.resume_skill}` : ''}
          </span>
        ))}
      </div>
      <div>
        <span className="mr-2 text-slate-400 dark:text-slate-500">Missing</span>
        {missing.length === 0 ? '—' : missing.map((s) => (
          <span key={s} className="mr-1 inline-block rounded bg-red-50 px-1.5 py-0.5 text-red-700 dark:bg-red-900/30 dark:text-red-300">{s}</span>
        ))}
      </div>
      <div>
        <span className="mr-2 text-slate-400 dark:text-slate-500">Experience</span>
        {need ? `${have ?? 'not stated'} (job asks for ${need})` : (have ?? 'not stated')}
      </div>
    </div>
  )
}

// active=false skips fetching — used so a closed/hidden modal doesn't fire
// a request, same intent as the old `open && canManage` guard it replaces.
// fullPage=true drops the height cap / scroll box for use on a dedicated
// applicants page instead of inside a cramped modal.
export default function ApplicantsPanel({ job, active = true, fullPage = false }) {
  const { showToast } = useToast()
  const [applicants, setApplicants] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!active || !job) {
      setApplicants([])
      return
    }
    setLoading(true)
    setError(null)
    fetchJobApplications(job.id)
      .then(setApplicants)
      .catch(() => setError('Could not load applicants.'))
      .finally(() => setLoading(false))
  }, [active, job])

  const [openingResumeId, setOpeningResumeId] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [rescoring, setRescoring] = useState(false)

  // While any row is still being scored, quietly re-fetch every few seconds
  // (max ~1 min) so scores appear and the list re-sorts without a reload.
  const anyPending = applicants.some((a) => a.match_status === 'pending')
  useEffect(() => {
    if (!active || !job || !anyPending) return undefined
    let tries = 0
    const timer = setInterval(() => {
      tries += 1
      fetchJobApplications(job.id).then(setApplicants).catch(() => {})
      if (tries >= 12) clearInterval(timer)
    }, 5000)
    return () => clearInterval(timer)
  }, [active, job, anyPending])

  const handleRescore = async () => {
    setRescoring(true)
    try {
      await rescoreJobApplications(job.id)
      setApplicants((prev) => prev.map((a) => ({ ...a, match_status: 'pending' })))
      showToast('Re-scoring applicants…', 'success')
    } catch {
      showToast('Could not start re-scoring.', 'error')
    } finally {
      setRescoring(false)
    }
  }

  const handleViewResume = async (applicationId, resumeId) => {
    setOpeningResumeId(applicationId)
    try {
      await openResumeFile(resumeId)
    } catch {
      showToast('Could not open that resume.', 'error')
    } finally {
      setOpeningResumeId(null)
    }
  }

  const handleStatusChange = async (applicationId, status) => {
    setApplicants((prev) => prev.map((a) => (a.id === applicationId ? { ...a, status } : a)))
    try {
      await updateApplicationStatus(applicationId, status)
      showToast('Applicant status updated.', 'success')
    } catch (err) {
      showToast('Could not update applicant status.', 'error')
      if (job) fetchJobApplications(job.id).then(setApplicants).catch(() => {})
    }
  }

  return (
    <div>
      <dt className="mb-2 flex items-center justify-between text-xs text-slate-400 dark:text-slate-500">
        <span>Applicants ({applicants.length}) · best match first</span>
        {applicants.length > 0 && (
          <button onClick={handleRescore} disabled={rescoring} className="font-medium text-slate-600 underline hover:no-underline disabled:opacity-50 dark:text-slate-300">
            {rescoring ? 'Queuing…' : 'Re-score'}
          </button>
        )}
      </dt>
      {loading ? (
        <div className="flex justify-center py-4"><Spinner size="sm" label="Loading applicants" /></div>
      ) : error ? (
        <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
      ) : applicants.length === 0 ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">No applications yet.</p>
      ) : (
        <div className={`rounded border border-slate-100 dark:border-slate-700 ${fullPage ? '' : 'max-h-52 overflow-y-auto'}`}>
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Applicant</th>
                <th className="px-3 py-2 font-medium">Match</th>
                <th className="px-3 py-2 font-medium">Applied</th>
                <th className="px-3 py-2 font-medium">Resume</th>
                <th className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {applicants.map((a) => (
                <Fragment key={a.id}>
                <tr className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">
                    {a.applicant_name || a.applicant_email}
                  </td>
                  <td className="px-3 py-2">
                    <ScoreBadge applicant={a} />
                    {a.match_details && (
                      <button onClick={() => setExpandedId(expandedId === a.id ? null : a.id)} className="ml-2 text-slate-500 underline hover:no-underline dark:text-slate-400">
                        {expandedId === a.id ? 'Hide' : 'Why?'}
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-500 dark:text-slate-400">
                    {new Date(a.applied_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2">
                    {a.resume_id ? (
                      <button onClick={() => handleViewResume(a.id, a.resume_id)} disabled={openingResumeId === a.id} className="font-medium text-slate-700 underline hover:no-underline disabled:opacity-50 dark:text-slate-300">
                        {openingResumeId === a.id ? 'Opening…' : 'View'}
                      </button>
                    ) : (
                      <span className="text-slate-400 dark:text-slate-500">No resume</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <select
                      value={a.status}
                      onChange={(e) => handleStatusChange(a.id, e.target.value)}
                      className="rounded border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                    >
                      {APPLICATION_STATUS_OPTIONS.map((s) => (
                        <option key={s} value={s}>{formatEnumLabel(s)}</option>
                      ))}
                    </select>
                  </td>
                </tr>
                {expandedId === a.id && (
                  <tr className="bg-slate-50/60 dark:bg-slate-800/40">
                    <td colSpan={5} className="px-3 py-2"><MatchDetails details={a.match_details} /></td>
                  </tr>
                )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}