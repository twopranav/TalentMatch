import { useEffect, useState } from 'react'
import Spinner from '../ui/Spinner'
import { useToast } from '../ui/Toast'
import { fetchJobApplications, updateApplicationStatus } from '../../api/applications'
import { formatEnumLabel } from '../../utils/format'
import { openResumeFile } from '../../api/resumes'

const APPLICATION_STATUS_OPTIONS = ['applied', 'under_review', 'shortlisted', 'rejected', 'hired']

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
      <dt className="mb-2 text-xs text-slate-400 dark:text-slate-500">Applicants ({applicants.length})</dt>
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
                <th className="px-3 py-2 font-medium">Applied</th>
                <th className="px-3 py-2 font-medium">Resume</th>
                <th className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {applicants.map((a) => (
                <tr key={a.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">
                    {a.applicant_name || a.applicant_email}
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
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}