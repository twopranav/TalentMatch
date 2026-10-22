import { useEffect, useState } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import { fetchJob } from '../api/jobs'
import { useAuth } from '../context/AuthContext'
import BulkApplyPanel from '../components/jobs/BulkApplyPanel'
import ApplicantsPanel from '../components/jobs/ApplicantsPanel'
import Spinner from '../components/ui/Spinner'
import InterviewingPanel from '../components/jobs/InterviewingPanel'
import { canWriteJob } from '../utils/permissions'
import { formatEnumLabel, getErrorMessage } from '../utils/format'
import PageHeader from '../components/ui/PageHeader'
import StatusBadge from '../components/ui/StatusBadge'


const TABS = [
  { key: 'all', label: 'Applicants' },
  { key: 'shortlisted', label: 'Shortlist' },
  { key: 'interviewing', label: 'Interviewing' },
]

// Dedicated page (meant to be opened via window.open in a new tab, not
// rendered inline) so a recruiter — or a future matching model reading this
// same route — has the JD and every applicant's resume link on one screen,
// instead of a cramped modal with a scrollable table.
export default function JobApplicants() {
  const { jobId } = useParams()
  const { user } = useAuth()
  const [refreshKey, setRefreshKey] = useState(0)
  const [allApplicantCount, setAllApplicantCount] = useState(null)
  const [shortlistedCount, setShortlistedCount] = useState(null)
  const [interviewingCount, setInterviewingCount] = useState(null)
  // The tab lives in the URL (?tab=shortlisted) so it survives a refresh and can be linked to.
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = TABS.some((t) => t.key === searchParams.get('tab')) ? searchParams.get('tab') : 'all'
  const counts = { all: allApplicantCount, shortlisted: shortlistedCount, interviewing: interviewingCount }
  const selectTab = (key) => {
    setSearchParams(key === 'all' ? {} : { tab: key }, { replace: true })
  }
  const [job, setJob] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    document.title = job?.title ? `${job.title} · Applicants — TalentMatch` : 'Applicants — TalentMatch'
    return () => { document.title = 'TalentMatch' }
  }, [job?.title])

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchJob(jobId)
      .then(setJob)
      .catch((err) => setError(getErrorMessage(err, 'Could not load this job.')))
      .finally(() => setLoading(false))
  }, [jobId])

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner size="lg" label="Loading job" />
      </div>
    )
  }

  if (error || !job) {
    return (
      <div className="mx-auto max-w-[1440px] px-8 py-8">
 <PageHeader eyebrow="Recruiting" title="Applicants unavailable" description={error || 'This job could not be found.'} />
        <Link to="/jobs" className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-indigo-200 hover:text-indigo-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:text-indigo-300">← Back to jobs</Link>
      </div>
    )
  }

  const canBulkApply = canWriteJob(user, job)
  const backTo = canBulkApply ? '/jobs/mine' : '/jobs'

  return (
    <div className="mx-auto max-w-[1440px] px-8 py-8">
      <PageHeader
        eyebrow="Recruiting"
        title={job.title}
        description={[job.location, formatEnumLabel(job.employment_type), formatEnumLabel(job.remote_type)].filter(Boolean).join(' · ')}
        meta={<StatusBadge status={job.status}>{formatEnumLabel(job.status)}</StatusBadge>}
        action={<Link to={backTo} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-indigo-200 hover:text-indigo-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:text-indigo-300">{canBulkApply ? '← My jobs' : '← All jobs'}</Link>}
      />

      {canBulkApply && (
        job.status === 'published' ? (
          <BulkApplyPanel job={job} onApplied={() => setRefreshKey((k) => k + 1)} />
        ) : (
          <p className="mb-6 text-xs text-slate-500 dark:text-slate-400">
            Publish this job to add resumes from your library as applicants.
          </p>
        )
      )}

      <div className="rounded-2xl border border-slate-200/80 bg-[#fbfaf7]/95 p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/90">
        <div role="tablist" aria-label="Applicant views" className="mb-4 flex gap-1 border-b border-slate-200 dark:border-slate-800">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              id={`applicants-tab-${t.key}`}
              aria-selected={tab === t.key}
              aria-controls={`applicants-panel-${t.key}`}
              onClick={() => selectTab(t.key)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${
                tab === t.key
                  ? 'border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300'
                  : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
              }`}
            >
              {counts[t.key] != null ? `${t.label} (${counts[t.key]})` : t.label}
            </button>
          ))}
        </div>

        {/* Both panels stay mounted so each keeps its own filters and page when
            you switch tabs; only the visible one fetches (active) and it
            refreshes on becoming visible, so a status change made in the other
            tab always shows up. */}
        <div role="tabpanel" id="applicants-panel-all" aria-labelledby="applicants-tab-all" hidden={tab !== 'all'}>
          <ApplicantsPanel job={job} active={tab === 'all'} fullPage refreshKey={refreshKey} onTotalChange={setAllApplicantCount} />
        </div>
        <div role="tabpanel" id="applicants-panel-shortlisted" aria-labelledby="applicants-tab-shortlisted" hidden={tab !== 'shortlisted'}>
          <ApplicantsPanel job={job} mode="shortlisted" active={tab === 'shortlisted'} fullPage refreshKey={refreshKey} onTotalChange={setShortlistedCount} />
        </div>
        <div role="tabpanel" id="applicants-panel-interviewing" aria-labelledby="applicants-tab-interviewing" hidden={tab !== 'interviewing'}>
          <InterviewingPanel job={job} active={tab === 'interviewing'} refreshKey={refreshKey} onTotalChange={setInterviewingCount} />
        </div>
      </div>
    </div>
  )
}