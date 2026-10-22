import { useMemo, useState } from 'react'
import { useMyApplications } from '../hooks/useApplications'
import { fetchJob } from '../api/jobs'
import JobDetailsModal from '../components/jobs/JobDetailsModal'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import { withdrawApplication } from '../api/applications'
import Spinner from '../components/ui/Spinner'
import StatusBadge from '../components/ui/StatusBadge'
import PageHeader from '../components/ui/PageHeader'
import { useToast } from '../components/ui/Toast'
import { formatEnumLabel } from '../utils/format'
import AddToCalendar from '../components/ui/AddToCalendar'

const STAGES = [
  { key: 'applied', label: 'Applied' },
  { key: 'under_review', label: 'Reviewing' },
  { key: 'shortlisted', label: 'Shortlisted' },
  { key: 'interview_scheduled', label: 'Interview' },
  { key: 'hired', label: 'Hired' },
]

function applicationStage(app) {
  if (app.status === 'hired') return 'hired'
  if (app.shortlist_stage === 'interview_scheduled' || app.stage === 'interview_scheduled' || app.interview_at) return 'interview_scheduled'
  if (app.status === 'shortlisted') return 'shortlisted'
  if (app.status === 'under_review') return 'under_review'
  return 'applied'
}

function StageTimeline({ application }) {
  const activeStage = applicationStage(application)
  const activeIndex = STAGES.findIndex((stage) => stage.key === activeStage)
  const rejected = application.status === 'rejected' || application.shortlist_stage === 'rejected' || application.stage === 'rejected'

  return (
    <div className="mt-4 flex items-start" aria-label={`Application stage: ${rejected ? 'Not proceeding' : STAGES[activeIndex]?.label}`}>
      {STAGES.map((stage, index) => {
        const complete = !rejected && index < activeIndex
        const current = !rejected && index === activeIndex
        return (
          <div key={stage.key} className="relative flex min-w-0 flex-1 flex-col items-center text-center">
            {index > 0 && <span className={`absolute right-1/2 top-[9px] h-px w-full ${complete || current ? 'bg-indigo-500' : 'bg-slate-200 dark:bg-slate-700'}`} aria-hidden="true" />}
            <span className={`relative z-[1] flex h-[18px] w-[18px] items-center justify-center rounded-full border text-[9px] font-bold ${complete ? 'border-indigo-600 bg-indigo-600 text-white' : current ? 'border-indigo-600 bg-indigo-50 text-indigo-700 ring-4 ring-indigo-500/10 dark:bg-indigo-950 dark:text-indigo-200' : 'border-slate-300 bg-[#fbfaf7] text-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-500'}`}>
              {complete ? '✓' : index + 1}
            </span>
            <span className={`mt-1.5 text-[10px] ${current ? 'font-semibold text-indigo-700 dark:text-indigo-300' : complete ? 'text-slate-600 dark:text-slate-300' : 'text-slate-400 dark:text-slate-500'}`}>{stage.label}</span>
          </div>
        )
      })}
      {rejected && <StatusBadge status="rejected" className="ml-3 shrink-0 self-center">Not proceeding</StatusBadge>}
    </div>
  )
}

export default function AppliedJobs() {
  const { applications, loading, error, refetch } = useMyApplications()
  const { showToast } = useToast()
  const [selectedJob, setSelectedJob] = useState(null)
  const [selectedApplication, setSelectedApplication] = useState(null)
  const [openingId, setOpeningId] = useState(null)
  const [activeFilter, setActiveFilter] = useState('all')
  const [withdrawTarget, setWithdrawTarget] = useState(null)
  const [withdrawingId, setWithdrawingId] = useState(null)

  const counts = useMemo(() => ({
    all: applications.length,
    applied: applications.filter((app) => app.status === 'applied').length,
    under_review: applications.filter((app) => app.status === 'under_review').length,
    shortlisted: applications.filter((app) => app.status === 'shortlisted').length,
    interview_scheduled: applications.filter((app) => app.shortlist_stage === 'interview_scheduled' || app.stage === 'interview_scheduled' || Boolean(app.interview_at)).length,
    hired: applications.filter((app) => app.status === 'hired').length,
    rejected: applications.filter((app) => app.status === 'rejected' || app.shortlist_stage === 'rejected' || app.stage === 'rejected').length,
  }), [applications])

  const filteredApplications = useMemo(() => activeFilter === 'all'
    ? applications
    : applications.filter((app) => activeFilter === 'interview_scheduled'
      ? app.shortlist_stage === 'interview_scheduled' || app.stage === 'interview_scheduled' || Boolean(app.interview_at)
      : activeFilter === 'rejected'
        ? app.status === 'rejected' || app.shortlist_stage === 'rejected' || app.stage === 'rejected'
        : activeFilter === 'shortlisted'
          ? app.status === 'shortlisted'
          : app.status === activeFilter), [applications, activeFilter])

  const openJob = async (application) => {
    setOpeningId(application.id)
    try {
      const job = await fetchJob(application.job_id)
      setSelectedJob(job)
      setSelectedApplication(application)
    } catch {
      showToast('Could not load this job.', 'error')
    } finally {
      setOpeningId(null)
    }
  }

  const handleWithdraw = async () => {
    const target = withdrawTarget
    if (!target || withdrawingId) return
    setWithdrawingId(target.id)
    try {
      await withdrawApplication(target.id)
      showToast('Application withdrawn.', 'success')
      setWithdrawTarget(null)
      refetch()
    } catch {
      showToast('Could not withdraw this application.', 'error')
    } finally {
      setWithdrawingId(null)
    }
  }

  const filters = [
    ['all', 'All applications'], ['applied', 'Applied'], ['under_review', 'Reviewing'],
    ['shortlisted', 'Shortlisted'], ['interview_scheduled', 'Interview'], ['hired', 'Hired'], ['rejected', 'Not proceeding'],
  ]

  return (
    <div className="mx-auto max-w-[1440px] px-8 py-8">
      <PageHeader eyebrow="Candidate" title="Applied jobs" description="Track each application from submission through interview and decision." meta={<span className="text-xs text-slate-500 dark:text-slate-400">{applications.length} {applications.length === 1 ? 'application' : 'applications'}</span>} />

      <div className="mb-5 flex flex-wrap gap-2 border-b border-slate-200 pb-3 dark:border-slate-800" role="tablist" aria-label="Filter applications">
        {filters.map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={activeFilter === key} onClick={() => setActiveFilter(key)} className={`rounded-xl px-3 py-2 text-xs font-semibold transition ${activeFilter === key ? 'bg-indigo-600 text-white shadow-sm' : 'border border-slate-200 bg-white/80 text-slate-600 hover:border-indigo-200 hover:text-indigo-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:text-indigo-300'}`}>
            {label} <span className={`ml-1 tabular-nums ${activeFilter === key ? 'text-indigo-100' : 'text-slate-400 dark:text-slate-500'}`}>{counts[key]}</span>
          </button>
        ))}
      </div>

      {loading && <div className="flex justify-center py-16"><Spinner size="lg" label="Loading applications" /></div>}
      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}

      {!loading && !error && applications.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 px-6 py-16 text-center dark:border-slate-700"><p className="text-sm text-slate-500 dark:text-slate-400">You haven't applied to any jobs yet.</p></div>}
      {!loading && !error && applications.length > 0 && filteredApplications.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 px-6 py-14 text-center dark:border-slate-700"><p className="text-sm text-slate-500 dark:text-slate-400">There are no applications in this stage yet.</p></div>}

      {!loading && !error && filteredApplications.length > 0 && <div className="grid grid-cols-2 gap-4">
        {filteredApplications.map((app) => {
          const interviewAt = app.interview_at
          return <article key={app.id} className="rounded-2xl border border-slate-200/90 bg-[#fbfaf7]/95 p-5 shadow-sm transition hover:border-indigo-200 hover:shadow-md dark:border-slate-800 dark:bg-slate-900/90 dark:hover:border-indigo-800">
            <div className="flex items-start gap-4">
              <button type="button" onClick={() => openJob(app)} disabled={openingId === app.id} className="min-w-0 flex-1 text-left disabled:opacity-60">
                <div className="flex flex-wrap items-center gap-2"><h2 className="truncate font-semibold text-slate-900 dark:text-slate-100">{app.job_title || 'Job application'}</h2><StatusBadge status={app.status}>{formatEnumLabel(app.status)}</StatusBadge></div>
                <p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400">{[app.company, app.location].filter(Boolean).join(' · ') || 'Company details unavailable'}</p>
              </button>
              <div className="flex shrink-0 flex-col items-end gap-2">
                <span className="text-right text-[11px] text-slate-500 dark:text-slate-400">Applied<br />{new Date(app.applied_at).toLocaleDateString()}</span>
                {!['hired', 'rejected', 'withdrawn'].includes(app.status) && <button type="button" disabled={withdrawingId === app.id} onClick={() => setWithdrawTarget(app)} className="rounded-lg border border-red-200 px-2.5 py-1.5 text-[11px] font-semibold text-red-700 transition hover:bg-red-50 disabled:opacity-50 dark:border-red-900/70 dark:text-red-300 dark:hover:bg-red-950/50">{withdrawingId === app.id ? 'Withdrawing…' : 'Withdraw'}</button>}
              </div>
            </div>
            <StageTimeline application={app} />
            {interviewAt && <div className="mt-4 flex items-center justify-between gap-3 rounded-xl border border-indigo-100 bg-indigo-50/70 px-3 py-2.5 dark:border-indigo-900/70 dark:bg-indigo-950/40"><div><p className="text-xs font-semibold text-indigo-900 dark:text-indigo-200">Interview scheduled</p><p className="mt-0.5 text-xs text-indigo-800/80 dark:text-indigo-300/80">{new Date(interviewAt).toLocaleString()}</p></div><AddToCalendar event={{ title: `Interview — ${app.job_title || 'Job'}`, description: `Interview for ${app.job_title || 'a job application'}.`, start: interviewAt, location: app.location || '' }} /></div>}
          </article>
        })}
      </div>}

      <JobDetailsModal open={Boolean(selectedJob)} onClose={() => { setSelectedJob(null); setSelectedApplication(null) }} job={selectedJob} onEdit={() => {}} onChanged={() => {}} onDeleted={() => {}} myApplication={selectedApplication} onApplicationChanged={refetch} />
      <ConfirmDialog open={Boolean(withdrawTarget)} onClose={() => { if (!withdrawingId) setWithdrawTarget(null) }} onConfirm={handleWithdraw} title="Withdraw this application?" message={withdrawTarget ? `Your application for ${withdrawTarget.job_title || 'this job'} will be withdrawn.` : ''} confirmLabel="Withdraw application" destructive />
    </div>
  )
}
