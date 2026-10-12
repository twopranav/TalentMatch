import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import Spinner from '../ui/Spinner'
import { useToast } from '../ui/Toast'
import {
  fetchJobApplicationsPage,
  rescoreJobApplications,
  updateApplicationStatus,
  updateShortlistStage,
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
import { openResumeFile } from '../../api/resumes'

const PAGE_SIZE = 10

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

// active=false skips fetching — used so a closed/hidden modal doesn't fire
// a request, same intent as the old `open && canManage` guard it replaces.
// fullPage=true drops the height cap / scroll box for use on a dedicated
// applicants page instead of inside a cramped modal.
// mode='shortlisted' lists only shortlisted applicants (same pagination and
// filters) and adds the shortlist stage + interview time controls.
export default function ApplicantsPanel({ job, active = true, fullPage = false, refreshKey = 0, mode = 'all' }) {
  const { showToast } = useToast()
  const isShortlist = mode === 'shortlisted'
  const jobId = job?.id
  const [applicants, setApplicants] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const requestId = useRef(0)

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
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
      const result = await fetchJobApplicationsPage(jobId, params, PAGE_SIZE, (page - 1) * PAGE_SIZE)
      if (id !== requestId.current) return
      setApplicants(result.items)
      setTotal(result.total)
      // Rows may have disappeared under us (withdrawn, filtered out): step
      // back to the last real page instead of showing an empty one.
      const pages = Math.max(1, Math.ceil(result.total / PAGE_SIZE))
      if (page > pages) setPage(pages)
    } catch {
      if (id === requestId.current && showSpinner) setError('Could not load applicants.')
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [jobId, filters, page, isShortlist])

  useEffect(() => {
    if (!active || !jobId) {
      setApplicants([])
      setTotal(0)
      return
    }
    runFetch(true)
  }, [active, jobId, runFetch, refreshKey])

  const [openingResumeId, setOpeningResumeId] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [rescoring, setRescoring] = useState(false)

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
    setPage(1) // a new filter set always starts from its first page
  }

  const handleRescore = async () => {
    setRescoring(true)
    try {
      await rescoreJobApplications(jobId)
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
  const [scheduleValue, setScheduleValue] = useState('')
  const [savingSchedule, setSavingSchedule] = useState(false)

  const handleStageChange = async (application, stage) => {
    if (stage === 'interview_scheduled') {
      // An interview needs a date and time first; nothing changes until saved.
      setSchedulingId(application.id)
      setScheduleValue(isoToLocalInput(application.interview_at))
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

  const handleSaveInterview = async (applicationId) => {
    const iso = localInputToIso(scheduleValue)
    if (!iso) {
      showToast('Pick a date and time for the interview.', 'error')
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

  const offset = (page - 1) * PAGE_SIZE
  const shownFrom = total === 0 ? 0 : offset + 1
  const shownTo = offset + applicants.length

  return (
    <div>
      <dt className="mb-2 flex items-center justify-between text-xs text-slate-400 dark:text-slate-500">
        <span>
          {isShortlist ? 'Shortlisted' : 'Applicants'} ({total}){filtersActive ? ' matching filters' : ''} · best match first, ties by earliest applied
        </span>
        {total > 0 && (
          <button onClick={handleRescore} disabled={rescoring} className="font-medium text-slate-600 underline hover:no-underline disabled:opacity-50 dark:text-slate-300">
            {rescoring ? 'Queuing…' : 'Re-score all'}
          </button>
        )}
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
          <div className={`rounded border border-slate-100 dark:border-slate-700 ${fullPage ? '' : 'max-h-52 overflow-y-auto'} ${loading ? 'opacity-60' : ''}`}>
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
                <tr>
                  <th className="w-8 px-3 py-2 font-medium">#</th>
                  <th className="px-3 py-2 font-medium">Applicant</th>
                  <th className="px-3 py-2 font-medium">Match</th>
                  <th className="px-3 py-2 font-medium">Applied</th>
                  <th className="px-3 py-2 font-medium">Resume</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  {isShortlist && <th className="px-3 py-2 font-medium">Stage</th>}
                </tr>
              </thead>
              <tbody>
                {applicants.map((a, idx) => (
                  <Fragment key={a.id}>
                    <tr className="border-t border-slate-100 transition hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50">
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
                          {statusOptionsFor(a.status).map((s) => (
                            <option key={s} value={s}>{statusLabel(s)}</option>
                          ))}
                        </select>
                      </td>
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
                            </div>
                          )}
                        </td>
                      )}
                    </tr>
                    {isShortlist && schedulingId === a.id && (
                      <tr className="bg-slate-50/60 dark:bg-slate-800/40">
                        <td colSpan={7} className="px-4 py-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <label htmlFor={`interview-${a.id}`} className="text-xs font-medium text-slate-600 dark:text-slate-300">
                              Interview date &amp; time
                            </label>
                            <input
                              id={`interview-${a.id}`}
                              type="datetime-local"
                              value={scheduleValue}
                              onChange={(e) => setScheduleValue(e.target.value)}
                              className="rounded border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                            />
                            <button
                              type="button"
                              onClick={() => handleSaveInterview(a.id)}
                              disabled={savingSchedule || !scheduleValue}
                              className="rounded bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                            >
                              {savingSchedule ? 'Saving…' : 'Save'}
                            </button>
                            <button
                              type="button"
                              onClick={() => setSchedulingId(null)}
                              disabled={savingSchedule}
                              className="rounded px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                            >
                              Cancel
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                    {expandedId === a.id && (
                      <tr className="bg-slate-50/60 dark:bg-slate-800/40">
                        <td colSpan={isShortlist ? 7 : 6} className="px-4 py-3"><ScoreExplanation details={a.match_details} /></td>
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
    </div>
  )
}
