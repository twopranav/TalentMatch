import { useCallback, useEffect, useRef, useState } from 'react'
import Spinner from '../ui/Spinner'
import Pagination from '../ui/Pagination'
import { useToast } from '../ui/Toast'
import { useAuth } from '../../context/AuthContext'
import { fetchJobApplicationsPage, updateInterview } from '../../api/applications'
import { formatInterviewTime, isoToLocalInput, localInputToIso } from '../../utils/applicantStatus'
import { getErrorMessage } from '../../utils/format'
import { canWriteJob } from '../../utils/permissions'
import ApplicantNotesModal from './ApplicantNotesModal'

const PAGE_SIZE = 10
const OUTCOMES = [['scheduled', 'Scheduled'], ['rejected', 'Rejected'], ['hired', 'Hired']]
const FIELD = 'rounded border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100'

// Interviewing tab: everyone who was moved to Interviewing, with interview
// date/time, outcome (scheduled / rejected / hired) and notes.
export default function InterviewingPanel({ job, active = true, refreshKey = 0, onTotalChange }) {
  const { showToast } = useToast()
  const { user } = useAuth()
  const canWrite = canWriteJob(user, job)
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [notesFor, setNotesFor] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [draft, setDraft] = useState('')
  const requestId = useRef(0)

  const load = useCallback(async () => {
    const id = ++requestId.current
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      ;['scheduled', 'rejected', 'hired'].forEach((s) => params.append('interview_stage', s))
      const res = await fetchJobApplicationsPage(job.id, params, PAGE_SIZE, (page - 1) * PAGE_SIZE)
      if (id !== requestId.current) return
      setRows(res.items)
      setTotal(res.total)
      onTotalChange?.(res.total)
      const last = Math.max(1, Math.ceil(res.total / PAGE_SIZE))
      if (page > last) setPage(last)
    } catch (err) {
      if (id === requestId.current) setError(getErrorMessage(err, 'Could not load interviews.'))
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [job.id, page, onTotalChange])

  useEffect(() => { if (active) load() }, [active, load, refreshKey])

  const save = async (row, stage, interviewAt = null) => {
    try {
      await updateInterview(row.id, stage, interviewAt)
      showToast('Interview updated.', 'success')
      setEditingId(null)
      load()
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not update the interview.'), 'error')
    }
  }

  const startEdit = (row) => { setEditingId(row.id); setDraft(isoToLocalInput(row.interview_at)) }
  const saveDate = (row) => {
    const iso = localInputToIso(draft)
    if (!iso) { showToast('Select a valid interview date and time.', 'error'); return }
    save(row, row.interview_stage ?? 'scheduled', iso)
  }

  if (error) return <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>
  if (loading && rows.length === 0) return <div className="flex justify-center py-10"><Spinner label="Loading interviews" /></div>

  return (
    <div>
      {rows.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-500 dark:text-slate-400">
          No one is interviewing yet. Use “Move to interviewing” on the Shortlist tab.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Applicant</th>
                <th className="px-3 py-2 font-medium">AI score</th>
                <th className="px-3 py-2 font-medium">Interview</th>
                <th className="px-3 py-2 font-medium">Outcome</th>
                <th className="px-3 py-2 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => {
                const stage = a.interview_stage ?? 'scheduled'
                return (
                  <tr key={a.id} className={`border-t border-slate-100 dark:border-slate-800 ${stage === 'hired' ? 'bg-emerald-50/60 dark:bg-emerald-950/20' : stage === 'rejected' ? 'opacity-60' : ''}`}>
                    <td className="px-3 py-2">
                      <div className="font-medium text-slate-800 dark:text-slate-100">{a.applicant_name || a.applicant_email}</div>
                      {a.applicant_name && a.applicant_email && <div className="text-slate-400">{a.applicant_email}</div>}
                    </td>
                    <td className="px-3 py-2">{a.match_score != null ? `${Math.round(a.match_score)}%` : '—'}</td>
                    <td className="px-3 py-2">
                      {editingId === a.id ? (
                        <div className="flex items-center gap-2">
                          <input type="datetime-local" value={draft} onChange={(e) => setDraft(e.target.value)} className={FIELD} />
                          <button type="button" onClick={() => saveDate(a)} className="font-medium text-indigo-700 underline dark:text-indigo-300">Save</button>
                          <button type="button" onClick={() => setEditingId(null)} className="text-slate-500 underline">Cancel</button>
                        </div>
                      ) : (
                        <span>
                          {formatInterviewTime(a.interview_at) || 'Date not set'}
                          {canWrite && <button type="button" onClick={() => startEdit(a)} className="ml-2 underline hover:no-underline">{a.interview_at ? 'Change' : 'Set date'}</button>}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <select value={stage} disabled={!canWrite} onChange={(e) => save(a, e.target.value)} aria-label={`Outcome for ${a.applicant_name || a.applicant_email}`} className={FIELD}>
                        {OUTCOMES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <button type="button" onClick={() => setNotesFor(a)} className="font-medium text-slate-700 underline hover:no-underline dark:text-slate-300">Notes</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <Pagination page={page} totalPages={Math.max(1, Math.ceil(total / PAGE_SIZE))} onPageChange={setPage} disabled={loading} />
      <ApplicantNotesModal applicant={notesFor} onClose={() => setNotesFor(null)} />
    </div>
  )
}
