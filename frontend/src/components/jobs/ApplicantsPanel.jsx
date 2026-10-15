import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import Spinner from '../ui/Spinner'
import { useToast } from '../ui/Toast'
import { useAuth } from '../../context/AuthContext'
import { canWriteJob } from '../../utils/permissions'
import {
  fetchJobApplicationsPage,
  rescoreJobApplications,
  updateApplicationStatus,
  updateManualScore,
  updateShortlistStage,
  bulkUpdateApplicationStatus,
} from '../../api/applications'
import {
  SHORTLIST_STAGE_OPTIONS,
  formatInterviewTime,
  isoToLocalInput,
  localInputToIso,
  stageLabel,
  statusLabel,
  statusOptionsFor,
} from '../../utils/applicantStatus'
import { getErrorMessage } from '../../utils/format'
import { countActiveFilters, EMPTY_FILTERS, filtersToParams } from '../../utils/applicantFilters'
import Pagination from '../ui/Pagination'
import ApplicantFilters from './ApplicantFilters'
import ScoreExplanation from './ScoreExplanation'
import ApplicantNotesModal from './ApplicantNotesModal'
import { openResumeFile } from '../../api/resumes'
import ConfirmDialog from '../ui/ConfirmDialog'
import Button from '../ui/Button'
import { downloadCsv } from '../../utils/csv'
import { downloadInterviewIcs } from '../../utils/calendar'

const DEFAULT_PAGE_SIZE = 10

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
    <span className={`inline-block rounded-full px-2.5 py-0.5 font-semibold tabular-nums ${tone}`} title={state === 'pending' ? 'Re-scoring…' : undefined}>
      {Math.round(score)}%
    </span>
  )
}

// 1 decimal place at most, and no trailing ".0": 82.5 -> "82.5", 90 -> "90".
function formatManualScore(value) {
  return String(Math.round(value * 10) / 10)
}

// The recruiter's own optional score for one shortlisted applicant. Separate
// from the AI score shown beside it: saving or clearing this never changes
// the AI score. Shows the score (or "Set score"); clicking opens a small
// inline editor.
function ManualScoreCell({ applicant, onSaved }) {
  const { showToast } = useToast()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const current = applicant.manual_score
  const name = applicant.applicant_name || applicant.applicant_email

  const startEditing = () => {
    setValue(current == null ? '' : String(current))
    setEditing(true)
  }

  const save = async (next) => {
    setSaving(true)
    try {
      await updateManualScore(applicant.id, next)
      onSaved(applicant.id, next)
      setEditing(false)
      showToast(next == null ? 'Manual score cleared.' : 'Manual score saved.', 'success')
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not save the manual score.'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleSave = () => {
    const number = Number(value)
    // Number('') is 0, so a blank box has to be rejected explicitly or it
    // would quietly save a score of zero.
    if (value.trim() === '' || !Number.isFinite(number) || number < 0 || number > 100) {
      showToast('Enter a score from 0 to 100.', 'error')
      return
    }
    save(number)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleSave()
    } else if (e.key === 'Escape') {
      // Cancel the edit only; don't let Escape also close a parent popup.
      e.stopPropagation()
      setEditing(false)
    }
  }

  if (!editing) {
    return (
      <div className="flex items-center gap-2 whitespace-nowrap">
        {current != null && (
          <span
            className="inline-block rounded-full border border-indigo-200 px-2.5 py-0.5 font-semibold tabular-nums text-indigo-700 dark:border-indigo-800 dark:text-indigo-300"
            title="Entered by a recruiter"
          >
            {formatManualScore(current)}%
          </span>
        )}
        <button
          type="button"
          onClick={startEditing}
          aria-label={`${current == null ? 'Set' : 'Edit'} manual score for ${name}`}
          className="text-slate-500 underline hover:no-underline dark:text-slate-400"
        >
          {current == null ? 'Set score' : 'Edit'}
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <input
        type="number"
        min="0"
        max="100"
        step="any"
        inputMode="decimal"
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={saving}
        placeholder="0-100"
        aria-label={`Manual score for ${name}, 0 to 100`}
        className="no-number-spinner w-16 rounded border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      />
      <button
        type="button"
        onClick={handleSave}
        disabled={saving}
        className="rounded bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {saving ? 'Saving…' : 'Save'}
      </button>
      <button
        type="button"
        onClick={() => setEditing(false)}
        disabled={saving}
        className="rounded px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        Cancel
      </button>
      {current != null && (
        <button
          type="button"
          onClick={() => save(null)}
          disabled={saving}
          className="rounded px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
        >
          Clear
        </button>
      )}
    </div>
  )
}

// active=false skips fetching — used so a closed/hidden modal doesn't fire
// a request, same intent as the old `open && canManage` guard it replaces.
// fullPage=true drops the height cap / scroll box for use on a dedicated
// applicants page instead of inside a cramped modal.
// mode='shortlisted' lists only shortlisted applicants (same pagination and
// filters) and adds the shortlist stage + interview time controls.
export default function ApplicantsPanel({ job, active = true, fullPage = false, refreshKey = 0, mode = 'all', onTotalChange }) {
  const { showToast } = useToast()
  const { user: currentUser } = useAuth()
  // Mirrors the server: admins open resumes in their sub company, recruiters only on jobs they posted.
  const canOpenResume = canWriteJob(currentUser, job)
  const isShortlist = mode === 'shortlisted'
  const jobId = job?.id
  const [applicants, setApplicants] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const pageSize = DEFAULT_PAGE_SIZE
  const [selectedIds, setSelectedIds] = useState([])
  const [bulkStatus, setBulkStatus] = useState('under_review')
  const [bulkUpdating, setBulkUpdating] = useState(false)
  const [rescoreConfirmOpen, setRescoreConfirmOpen] = useState(false)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const requestId = useRef(0)

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const filtersActive = countActiveFilters(filters) > 0

  // One place that loads the current page with the current filters. Only the
  // newest request may update state, so a slow earlier response can't
  // overwrite a newer page/filter choice. Silent loads (polling, refreshes)
  // don't flash the spinner or the error message.
  const runFetch = useCallback(async (showSpinner) => {
    requestId.current += 1
    const id = requestId.current
    if (showSpinner) {
      setLoading(true)
      setError(null)
    }
    try {
      const params = filtersToParams(filters)
      if (isShortlist) params.set('status', 'shortlisted') // this tab is always just the shortlist
      const result = await fetchJobApplicationsPage(jobId, params, pageSize, (page - 1) * pageSize)
      if (id !== requestId.current) return
      setApplicants(result.items)
      setTotal(result.total)
      // Rows may have disappeared under us (withdrawn, filtered out): step
      // back to the last real page instead of showing an empty one.
      const pages = Math.max(1, Math.ceil(result.total / pageSize))
      if (page > pages) setPage(pages)
    } catch {
      if (id === requestId.current && showSpinner) setError('Could not load applicants.')
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [jobId, filters, page, pageSize, isShortlist])

  useEffect(() => {
    if (!active || !jobId) {
      setApplicants([])
      return
    }
    runFetch(true)
  }, [active, jobId, runFetch, refreshKey])

  useEffect(() => { if (active) onTotalChange?.(total) }, [total, onTotalChange, active])

  const [openingResumeId, setOpeningResumeId] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [rescoring, setRescoring] = useState(false)
  const [exportingCsv, setExportingCsv] = useState(false)
  const [notesFor, setNotesFor] = useState(null) // the applicant whose notes popup is open (shortlist tab)

  // While any row on this page is still being scored, quietly re-fetch every
  // few seconds (max ~1 min) so scores appear and the list re-sorts.
  const anyPending = applicants.some((a) => a.match_status === 'pending')
  useEffect(() => {
    if (!active || !jobId || !anyPending) return undefined
    let tries = 0
    const timer = setInterval(() => {
      tries += 1
      runFetch(false)
      if (tries >= 12) clearInterval(timer)
    }, 5000)
    return () => clearInterval(timer)
  }, [active, jobId, anyPending, runFetch])

  const handleFiltersChange = (next) => {
    setFilters(next)
    setPage(1)
    setSelectedIds([])
  }

  const handleExportCsv = async () => {
    if (!total || exportingCsv) return
    setExportingCsv(true)
    try {
      const params = filtersToParams(filters)
      if (isShortlist) params.set('status', 'shortlisted')
      const exportRows = []
      let offset = 0
      let exportTotal = total
      const limit = 200
      while (offset < exportTotal) {
        const result = await fetchJobApplicationsPage(jobId, params, limit, offset)
        exportRows.push(...result.items)
        exportTotal = result.total
        if (!result.items.length) break
        offset += result.items.length
      }
      const exported = downloadCsv(`applicants-${job?.title ?? jobId}-${isShortlist ? 'shortlisted' : 'all'}`.replace(/[^a-z0-9_-]+/gi, '-'), exportRows.map((item) => ({
        applicant_name: item.applicant_name ?? '',
        applicant_email: item.applicant_email ?? '',
        job_title: job?.title ?? '',
        application_status: item.status ?? '',
        shortlist_stage: item.shortlist_stage ?? '',
        applied_at: item.applied_at ?? '',
        interview_at: item.interview_at ?? '',
        match_score: item.match_score ?? '',
        manual_score: item.manual_score ?? '',
        resume_filename: item.resume_filename ?? item.original_filename ?? '',
      })))
      if (exported) showToast(`Exported ${exportRows.length} applicant records.`, 'success')
      else showToast('There are no applicant records to export.', 'info')
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not export applicant data.'), 'error')
    } finally {
      setExportingCsv(false)
    }
  }

  const handleRescore = async () => {
    setRescoring(true)
    try {
      const result = await rescoreJobApplications(jobId)
      if (result?.already_in_progress) {
        showToast('A rescore is already running.', 'info')
      } else {
        const queued = Number(result?.queued ?? result?.queued_count ?? result?.queued_applications ?? 0)
        if (queued > 0) {
          setApplicants((prev) => prev.map((applicant) => ({ ...applicant, match_status: 'pending' })))
          showToast(`Re-scoring queued for ${queued} applicant${queued === 1 ? '' : 's'}.`, 'success')
        } else {
          showToast('No applicants were queued for re-scoring.', 'info')
        }
      }
    } catch (err) {
      if (err.response?.status === 429) {
        const retryAfter = Number(err.response.headers?.['retry-after'] ?? 60)
        showToast(`Please wait ${retryAfter} seconds before starting another rescore.`, 'error', 7000)
      } else showToast(getErrorMessage(err, 'Could not start re-scoring.'), 'error')
    } finally { setRescoring(false); setRescoreConfirmOpen(false) }
  }

  const handleBulkUpdate = async () => {
    if (!selectedIds.length || !bulkStatus || bulkUpdating) return
    const prior = applicants.filter((applicant) => selectedIds.includes(applicant.id)).map((applicant) => ({ id: applicant.id, status: applicant.status }))
    setBulkUpdating(true)
    try {
      const response = await bulkUpdateApplicationStatus(jobId, selectedIds, bulkStatus)
      const outcomes = response?.results ?? response?.items ?? response?.items_results ?? []
      const successfulIds = outcomes.length
        ? outcomes.filter((item) => item.success === true || item.ok === true || item.status === 'success' || item.status === bulkStatus || item.updated === true).map((item) => item.application_id ?? item.id)
        : selectedIds.slice(0, Number(response?.updated_count ?? response?.updated ?? selectedIds.length))
      setApplicants((current) => current.map((applicant) => successfulIds.includes(applicant.id) ? { ...applicant, status: bulkStatus, shortlist_stage: bulkStatus === 'shortlisted' ? (applicant.shortlist_stage ?? 'shortlisted') : null, interview_at: bulkStatus === 'shortlisted' ? applicant.interview_at : null } : applicant))
      setSelectedIds([])
      const undo = async () => {
        const groups = new Map()
        for (const item of prior.filter((row) => successfulIds.includes(row.id))) groups.set(item.status, [...(groups.get(item.status) ?? []), item.id])
        try {
          await Promise.all([...groups.entries()].map(([oldStatus, ids]) => bulkUpdateApplicationStatus(jobId, ids, oldStatus)))
          showToast('Bulk status change undone.', 'info')
          runFetch(false)
        } catch (error) { showToast(getErrorMessage(error, 'Could not undo the bulk update.'), 'error') }
      }
      showToast(`Updated ${successfulIds.length} of ${selectedIds.length} selected applications.`, 'success', 6500, { label: 'Undo', onClick: undo })
      runFetch(false)
    } catch (err) {
      if (err.response?.status === 429) {
        const retryAfter = Number(err.response.headers?.['retry-after'] ?? 60)
        showToast(`Bulk triage is rate-limited. Try again in ${retryAfter} seconds.`, 'error', 7000)
      } else showToast(getErrorMessage(err, 'Could not update selected applications.'), 'error')
    } finally { setBulkUpdating(false) }
  }

  const pageIds = applicants.map((applicant) => applicant.id)
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.includes(id))
  const togglePageSelection = (checked) => setSelectedIds((current) => checked ? [...new Set([...current, ...pageIds])] : current.filter((id) => !pageIds.includes(id)))

  const handleManualScoreSaved = (applicationId, manualScore) => {
    setApplicants((prev) => prev.map((a) => (a.id === applicationId ? { ...a, manual_score: manualScore } : a)))
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
    setApplicants((prev) => prev.map((a) => {
      if (a.id !== applicationId || a.status === status) return a
      // Mirrors the server: entering the shortlist starts at the default
      // stage, leaving it clears the stage and interview time.
      return { ...a, status, shortlist_stage: status === 'shortlisted' ? 'shortlisted' : null, interview_at: null }
    }))
    try {
      await updateApplicationStatus(applicationId, status)
      showToast('Applicant status updated.', 'success')
      // With a status filter on (or on the shortlist tab, where moving
      // someone out removes them), the row may no longer belong in this view.
      if (isShortlist || filters.statuses.length) runFetch(false)
    } catch {
      showToast('Could not update applicant status.', 'error')
      runFetch(false)
    }
  }

  // --- Shortlist stage / interview scheduling (shortlist tab only) ---
  const [schedulingId, setSchedulingId] = useState(null)
  const [scheduleDate, setScheduleDate] = useState('')
  const [scheduleTime, setScheduleTime] = useState('')
  const [savingSchedule, setSavingSchedule] = useState(false)

  const handleStageChange = async (application, stage) => {
    if (stage === 'interview_scheduled') {
      // An interview needs a date and time first; nothing changes until saved.
      setSchedulingId(application.id)
      const localValue = isoToLocalInput(application.interview_at)
      setScheduleDate(localValue ? localValue.slice(0, 10) : '')
      setScheduleTime(localValue ? localValue.slice(11, 16) : '')
      return
    }
    setSchedulingId(null)
    setApplicants((prev) => prev.map((a) => (a.id === application.id ? { ...a, shortlist_stage: stage, interview_at: null } : a)))
    try {
      await updateShortlistStage(application.id, stage)
      showToast('Shortlist stage updated.', 'success')
      if (filters.stages.length) runFetch(false)
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not update shortlist stage.'), 'error')
      runFetch(false)
    }
  }

  const handleMoveToInterviewing = async (application) => {
    try {
      await updateApplicationStatus(application.id, 'interviewing')
      showToast('Moved to Interviewing.', 'success')
      runFetch(false)
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not move to interviewing.'), 'error')
    }
  }

  const handleSaveInterview = async (applicationId) => {
    if (!scheduleDate || !scheduleTime) {
      showToast('Select both an interview date and time.', 'error')
      return
    }
    const iso = localInputToIso(`${scheduleDate}T${scheduleTime}`)
    if (!iso) {
      showToast('Select a valid interview date and time.', 'error')
      return
    }
    setSavingSchedule(true)
    try {
      await updateShortlistStage(applicationId, 'interview_scheduled', iso)
      setApplicants((prev) => prev.map((a) => (a.id === applicationId ? { ...a, shortlist_stage: 'interview_scheduled', interview_at: iso } : a)))
      setSchedulingId(null)
      showToast('Interview scheduled.', 'success')
      if (filters.stages.length) runFetch(false)
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not schedule the interview.'), 'error')
    } finally {
      setSavingSchedule(false)
    }
  }

  // Shortlist tab has two extra columns (manual score, notes) on top of the usual six.
  const columnCount = isShortlist ? 9 : 7
  const offset = (page - 1) * pageSize
  const shownFrom = total === 0 ? 0 : offset + 1
  const shownTo = offset + applicants.length

  return (
    <div>
      <dt className="mb-2 flex items-center justify-between text-xs text-slate-400 dark:text-slate-500">
        <span>
          {isShortlist ? 'Shortlisted' : 'Applicants'} ({total}){filtersActive ? ' matching filters' : ''} · best AI score first, ties by earliest applied
        </span>
        <span className="flex items-center gap-3">
          {total > 0 && <button type="button" onClick={handleExportCsv} disabled={exportingCsv} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-semibold text-slate-700 transition hover:border-indigo-200 hover:text-indigo-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:text-indigo-300">{exportingCsv ? 'Exporting…' : 'Export CSV'}</button>}
          {total > 0 && <button type="button" onClick={() => setRescoreConfirmOpen(true)} disabled={rescoring} className="font-semibold text-indigo-700 underline hover:no-underline disabled:opacity-50 dark:text-indigo-300">{rescoring ? 'Queuing…' : 'Re-score all'}</button>}
        </span>
      </dt>

      {(total > 0 || filtersActive) && (
        <ApplicantFilters value={filters} onChange={handleFiltersChange} jdSkills={job?.skills_result || []} mode={mode} />
      )}

      {loading && applicants.length === 0 ? (
        <div className="flex justify-center py-4"><Spinner size="sm" label="Loading applicants" /></div>
      ) : error ? (
        <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
      ) : total === 0 ? (
        <p className="text-xs text-slate-400 dark:text-slate-500">
          {filtersActive
            ? 'No applicants match these filters.'
            : isShortlist
              ? 'No shortlisted applicants yet. Set an applicant\'s status to Shortlisted to see them here.'
              : 'No applications yet.'}
        </p>
      ) : (
        <>
          <div className={`rounded border border-slate-100 dark:border-slate-700 ${fullPage ? 'overflow-x-auto' : 'max-h-52 overflow-auto'} ${loading ? 'opacity-60' : ''}`}>
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
                <tr>
                  <th className="w-8 px-3 py-2 font-medium"><input type="checkbox" aria-label="Select all applicants on this page" checked={allPageSelected} onChange={(event) => togglePageSelection(event.target.checked)} disabled={isShortlist} /></th>
                  <th className="w-8 px-3 py-2 font-medium">#</th>
                  <th className="px-3 py-2 font-medium">Applicant</th>
                  <th className="px-3 py-2 font-medium">AI score</th>
                  {isShortlist && <th className="px-3 py-2 font-medium">Manual score</th>}
                  <th className="px-3 py-2 font-medium">Applied</th>
                  <th className="px-3 py-2 font-medium">Resume</th>
                  {!isShortlist && <th className="px-3 py-2 font-medium">Status</th>}
                  {isShortlist && <th className="px-3 py-2 font-medium">Stage</th>}
                  {isShortlist && <th className="px-3 py-2 font-medium">Notes</th>}
                </tr>
              </thead>
              <tbody>
                {applicants.map((a, idx) => (
                  <Fragment key={a.id}>
                    <tr
                      className={`border-t transition ${
                        isShortlist && a.shortlist_stage === 'rejected'
                          ? 'border-red-200 bg-red-50 hover:bg-red-100 dark:border-red-900/50 dark:bg-red-900/20 dark:hover:bg-red-900/30'
                          : 'border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50'
                      }`}
                    >
                      <td className="px-3 py-2"><input type="checkbox" aria-label={`Select ${a.applicant_name || a.applicant_email}`} checked={selectedIds.includes(a.id)} disabled={isShortlist} onChange={(event) => setSelectedIds((current) => event.target.checked ? [...new Set([...current, a.id])] : current.filter((id) => id !== a.id))} /></td>
                      <td className={`px-3 py-2 font-semibold tabular-nums ${offset + idx === 0 && a.match_score != null ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-400 dark:text-slate-500'}`}>
                        {offset + idx + 1}
                      </td>
                      <td className="px-3 py-2 font-medium text-slate-700 dark:text-slate-300">
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
                      {isShortlist && (
                        <td className="px-3 py-2">
                          <ManualScoreCell applicant={a} onSaved={handleManualScoreSaved} />
                        </td>
                      )}
                      <td className="px-3 py-2 text-slate-500 dark:text-slate-400">
                        {new Date(a.applied_at).toLocaleDateString()}
                      </td>
                      <td className="px-3 py-2">
                        {a.resume_id && canOpenResume ? (
                          <button onClick={() => handleViewResume(a.id, a.resume_id)} disabled={openingResumeId === a.id} className="font-medium text-slate-700 underline hover:no-underline disabled:opacity-50 dark:text-slate-300">
                            {openingResumeId === a.id ? 'Opening…' : 'View'}
                          </button>
                        ) : (
                          <span className="text-slate-400 dark:text-slate-500">{a.resume_id ? 'Restricted' : 'No resume'}</span>
                        )}
                      </td>
                      {!isShortlist && (
                        <td className="px-3 py-2">
                          <select
                            value={a.status}
                            onChange={(e) => handleStatusChange(a.id, e.target.value)}
                            className="rounded border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                          >
                            {statusOptionsFor(a.status).map((s) => (
                              <option key={s} value={s}>{statusLabel(s)}</option>
                            ))}
                          </select>
                        </td>
                      )}
                      {isShortlist && (
                        <td className="px-3 py-2">
                          <select
                            value={a.shortlist_stage ?? 'shortlisted'}
                            onChange={(e) => handleStageChange(a, e.target.value)}
                            aria-label={`Shortlist stage for ${a.applicant_name || a.applicant_email}`}
                            className="rounded border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                          >
                            {SHORTLIST_STAGE_OPTIONS.map((s) => (
                              <option key={s} value={s}>{stageLabel(s)}</option>
                            ))}
                          </select>
                          <button type="button" onClick={() => handleMoveToInterviewing(a)} className="ml-2 rounded-md border border-indigo-200 bg-white px-2 py-1 font-medium text-indigo-700 hover:bg-indigo-50 dark:border-indigo-800 dark:bg-slate-900 dark:text-indigo-300">
                            Move to interviewing
                          </button>
                          {a.shortlist_stage === 'interview_scheduled' && a.interview_at && (
                            <div className="mt-1 text-slate-500 dark:text-slate-400">
                              {formatInterviewTime(a.interview_at)}
                              <button
                                type="button"
                                onClick={() => handleStageChange(a, 'interview_scheduled')}
                                className="ml-2 underline hover:no-underline"
                              >
                                Change
                              </button>
                              <button
                                type="button"
                                onClick={() => downloadInterviewIcs({ title: `TalentMatch interview — ${job?.title ?? 'Job'}`, description: `Interview with ${a.applicant_name ?? a.applicant_email ?? 'candidate'} for ${job?.title ?? 'a job'}.`, start: a.interview_at, location: job?.location ?? '' })}
                                className="ml-2 inline-flex rounded-md border border-indigo-200 bg-white px-2 py-1 font-medium text-indigo-700 hover:bg-indigo-50 dark:border-indigo-800 dark:bg-slate-900 dark:text-indigo-300 dark:hover:bg-indigo-950"
                              >
                                Add to calendar
                              </button>
                            </div>
                          )}
                        </td>
                      )}
                      {isShortlist && (
                        <td className="px-3 py-2">
                          <button
                            type="button"
                            onClick={() => setNotesFor(a)}
                            aria-label={`Notes for ${a.applicant_name || a.applicant_email}`}
                            className="font-medium text-slate-700 underline hover:no-underline dark:text-slate-300"
                          >
                            Notes
                          </button>
                        </td>
                      )}
                    </tr>
                    {isShortlist && schedulingId === a.id && (
                      <tr className="bg-slate-50/60 dark:bg-slate-800/40">
                        <td colSpan={columnCount} className="px-4 py-3">
                          <div className="flex flex-wrap items-end gap-4">
                            <div>
                              <label htmlFor={`interview-date-${a.id}`} className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-slate-300">Interview date</label>
                              <input id={`interview-date-${a.id}`} type="date" value={scheduleDate} onChange={(e) => setScheduleDate(e.target.value)} className="interview-date-input rounded-xl border border-slate-300 bg-[#fbfaf7] px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100" />
                            </div>
                            <div>
                              <label htmlFor={`interview-time-${a.id}`} className="mb-1.5 block text-xs font-medium text-slate-600 dark:text-slate-300">Interview time</label>
                              <input id={`interview-time-${a.id}`} type="time" value={scheduleTime} onChange={(e) => setScheduleTime(e.target.value)} className="interview-time-input rounded-xl border border-slate-300 bg-[#fbfaf7] px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100" />
                            </div>
                            <button type="button" onClick={() => handleSaveInterview(a.id)} disabled={savingSchedule || !scheduleDate || !scheduleTime} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 disabled:cursor-not-allowed disabled:opacity-50">{savingSchedule ? 'Saving…' : 'Save interview'}</button>
                            <button type="button" onClick={() => setSchedulingId(null)} disabled={savingSchedule} className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">Cancel</button>
                          </div>
                        </td>
                      </tr>
                    )}
                    {expandedId === a.id && (
                      <tr className="bg-slate-50/60 dark:bg-slate-800/40">
                        <td colSpan={columnCount} className="px-4 py-3"><ScoreExplanation details={a.match_details} /></td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-center text-xs text-slate-400 dark:text-slate-500">
            Showing {shownFrom}–{shownTo} of {total}
          </p>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} disabled={loading} />
        </>
      )}
      {!isShortlist && selectedIds.length > 0 && <div className="sticky bottom-3 z-20 mt-4 flex items-center justify-between gap-4 rounded-2xl border border-indigo-200 bg-white/95 px-5 py-3 shadow-xl backdrop-blur dark:border-indigo-900 dark:bg-slate-900/95"><div><p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{selectedIds.length} selected</p><p className="text-xs text-slate-500 dark:text-slate-400">Apply one status to the selected applications.</p></div><div className="flex items-center gap-3"><select value={bulkStatus} onChange={(event) => setBulkStatus(event.target.value)} aria-label="Bulk application status" className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"><option value="applied">Applied</option><option value="under_review">Reviewing</option><option value="shortlisted">Shortlisted</option><option value="rejected">Not proceeding</option><option value="hired">Hired</option></select><Button variant="secondary" size="sm" onClick={() => setSelectedIds([])} disabled={bulkUpdating}>Clear selection</Button><Button size="sm" onClick={handleBulkUpdate} disabled={bulkUpdating}>{bulkUpdating ? 'Updating…' : 'Update status'}</Button></div></div>}
      <ConfirmDialog open={rescoreConfirmOpen} onClose={() => setRescoreConfirmOpen(false)} onConfirm={handleRescore} title="Re-score all applicants?" message={`This will queue a rescore for all ${total} applicants associated with this job.`} confirmLabel="Re-score all" busy={rescoring} />
      {isShortlist && <ApplicantNotesModal applicant={notesFor} onClose={() => setNotesFor(null)} />}
    </div>
  )
}