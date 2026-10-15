import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { fetchMe } from '../api/users'
import { fetchOverview, fetchAdminHealthMetrics } from '../api/overview'
import { useResumes } from '../hooks/useResumes'
import { formatEnumLabel } from '../utils/format'
import Spinner from '../components/ui/Spinner'
import StatusBadge from '../components/ui/StatusBadge'
import Button from '../components/ui/Button'
import PageHeader from '../components/ui/PageHeader'
import { fetchJobsPage } from '../api/jobs'
import { useMyApplications } from '../hooks/useApplications'
import { downloadInterviewIcs } from '../utils/calendar'

function getGreetingPeriod(date = new Date()) {
  const hour = date.getHours()
  if (hour < 12) return 'Morning'
  if (hour < 18) return 'Afternoon'
  return 'Evening'
}

const ROLE_LABELS = { user: 'Applicant', recruiter: 'Recruiter', admin: 'Administrator', superuser: 'Superuser' }

function read(data, ...keys) {
  for (const key of keys) {
    const value = key.split('.').reduce((current, part) => current?.[part], data)
    if (value !== undefined && value !== null) return value
  }
  return undefined
}

function rows(value) {
  if (Array.isArray(value)) return value
  if (Array.isArray(value?.items)) return value.items
  if (Array.isArray(value?.results)) return value.results
  if (value && typeof value === 'object') return Object.entries(value).map(([key, item]) => item && typeof item === 'object' ? { task: key, ...item } : { task: key, status: item })
  return []
}

function count(value) {
  if (typeof value === 'number') return value
  if (Array.isArray(value)) return value.length
  if (value && typeof value === 'object') return Object.values(value).reduce((sum, item) => sum + (Number(item) || 0), 0)
  return Number(value ?? 0)
}

function Metric({ label, value, detail, tone = 'indigo' }) {
  const accent = tone === 'red' ? 'border-red-300/70 dark:border-red-900' : 'border-indigo-300/70 dark:border-indigo-800'
  return <div className={`rounded-2xl border ${accent} bg-white/90 p-5 shadow-sm dark:bg-slate-900/80`}><p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500 dark:text-slate-400">{label}</p><p className="mt-2 font-display text-4xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{value ?? '—'}</p>{detail && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{detail}</p>}</div>
}

function Section({ title, action, children }) {
  return <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/90 shadow-sm dark:border-slate-800 dark:bg-slate-900/80"><div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-800"><h2 className="font-display text-2xl font-semibold text-slate-900 dark:text-slate-100">{title}</h2>{action}</div><div className="p-5">{children}</div></section>
}

function SimpleRows({ items, empty, render }) {
  if (!items.length) {
    return (
      <p className="py-3 text-sm text-slate-500 dark:text-slate-400">
        {empty}
      </p>
    )
  }

  return (
    <div className="divide-y divide-slate-100 dark:divide-slate-800">
      {items.map((item, index) => (
        <div
          key={`${item.id ?? item.job_id ?? item.application_id ?? 'row'}-${index}`}
          className="py-3 first:pt-0 last:pb-0"
        >
          {render(item)}
        </div>
      ))}
    </div>
  )
}

export default function Overview() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [profileName, setProfileName] = useState('')
  const [greetingPeriod, setGreetingPeriod] = useState(() => getGreetingPeriod())
  const [recruiterJobDetails, setRecruiterJobDetails] = useState([])
  const [recruiterJobCount, setRecruiterJobCount] = useState(null)

  const { resumes } = useResumes({ enabled: user?.role === 'user' })
  const { applications: myApplications } = useMyApplications(user?.role === 'user')
  const applicant = user?.role === 'user'
  const recruiter = user?.role === 'recruiter'
  const admin = ['admin', 'superuser'].includes(user?.role)

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    fetchOverview()
      .then(setData)
      .catch(() => setError('Could not load the overview. Please try again.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    let cancelled = false
    fetchMe()
      .then((profile) => { if (!cancelled) setProfileName((profile?.full_name ?? '').trim()) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const updateGreeting = () => setGreetingPeriod(getGreetingPeriod())
    updateGreeting()
    const interval = window.setInterval(updateGreeting, 60000)
    window.addEventListener('focus', updateGreeting)

    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', updateGreeting)
    }
  }, [])

  useEffect(() => {
    if (!admin) return undefined

    const refreshHealth = () => fetchAdminHealthMetrics().then(setHealth).catch(() => {})
    refreshHealth()

    const interval = window.setInterval(refreshHealth, 60000)
    window.addEventListener('focus', refreshHealth)

    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', refreshHealth)
    }
  }, [admin])

  // Fetch the recruiter’s jobs and the total count reported by the API.
  useEffect(() => {
    if (!recruiter) return undefined

    let cancelled = false

    fetchJobsPage({ created_by: 'me', limit: 100, offset: 0 })
      .then((result) => {
        const jobs = rows(result?.items ?? result?.results ?? result?.jobs ?? result)
        const reportedTotal = result?.total ?? result?.total_count ?? result?.totalCount
        const parsedTotal = Number(reportedTotal)

        if (!cancelled) {
          setRecruiterJobDetails(jobs)
          setRecruiterJobCount(
            reportedTotal != null && Number.isFinite(parsedTotal) && parsedTotal >= 0
              ? parsedTotal
              : jobs.length
          )
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRecruiterJobDetails([])
          setRecruiterJobCount(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [recruiter])

  const candidate = read(data, 'applicant', 'candidate', 'data.applicant') ?? data ?? {}
  const recruiterData = read(data, 'recruiter', 'data.recruiter') ?? data ?? {}
  const adminData = read(data, 'admin', 'data.admin') ?? data ?? {}
  const ownJobs = rows(read(recruiterData, 'jobs', 'own_jobs', 'my_jobs'))
  const funnelCounts = read(recruiterData, 'funnel')
  const quickActions = read(recruiterData, 'quick_actions') ?? {}
  const appliedJobIds = useMemo(() => new Set(myApplications.map((item) => String(item.job_id))), [myApplications])

  const upcoming = rows(read(applicant ? candidate : recruiterData, 'upcoming_interviews', 'interviews.upcoming'))
  const recentApplications = rows(read(candidate, 'recent_applications', 'applications.recent'))
  const newestJobs = rows(read(candidate, 'newest_jobs', 'jobs.newest', 'latest_jobs'))
  const applicationCounts = read(candidate, 'application_status_counts', 'applications_by_status', 'application_counts') ?? {}
  const onboarding = read(candidate, 'onboarding_checklist', 'onboarding', 'checklist')
  const resumeStatus = read(candidate, 'resume_status') ?? (resumes.length ? (resumes[0]?.status ?? 'uploaded') : 'missing')
  const pendingRequestRaw = read(adminData, 'pending_recruiter_requests', 'pending_recruiter_requests_count', 'recruiter_requests_pending') ?? 0
  const pendingRequests = count(pendingRequestRaw)
  const unsetTasks = rows(read(adminData, 'unset_llm_task_names', 'unset_llm_tasks', 'llm_tasks_unset', 'unset_models'))
  const unsetTaskCount = Math.max(unsetTasks.length, Number(read(adminData, 'unset_llm_tasks_count', 'llm_tasks_unset_count', 'unset_models_count') ?? 0))
  const healthQueueDepth = read(health, 'queue_depth', 'system_queue_depth', 'queue.depth')
  const healthQuota = read(health, 'quota_usage', 'quota')
  const stuckRows = rows(read(health, 'stuck_rows', 'stuck_tasks', 'stuck_records'))
  const redisStatus = read(health, 'redis_status', 'redis.status', 'redis')
  const probes = rows(read(health, 'llm_tasks', 'task_results', 'last_probe_results', 'probes'))
  const pendingRecruiters = rows(read(adminData, 'pending_recruiters'))
  const isSuperuser = user?.role === 'superuser'
  const auditActivity = rows(read(adminData, 'recent_audit_activity', 'recent_audit', 'audit_activity'))
  const quota = read(adminData, 'quota_usage', 'quota')
  const queueDepth = read(adminData, 'system_queue_depth', 'queue_depth', 'queue.depth')

  const weekEnd = Date.now() + 7 * 24 * 60 * 60 * 1000
  const interviewsThisWeek = upcoming.filter((item) => {
    const time = new Date(item.interview_at ?? item.scheduled_at).getTime()
    return Number.isFinite(time) && time >= Date.now() && time <= weekEnd
  })

  const attentionJobs = (recruiterJobDetails.length ? recruiterJobDetails : ownJobs).flatMap((job) => {
    const aggregate = ownJobs.find((item) => String(item.id) === String(job.id)) ?? {}
    const hasApplicants = count(job.applicant_count ?? job.applicants_count ?? aggregate.applicant_count ?? aggregate.applicants_count) > 0
    const hasJd = Boolean(job.jd_raw_text || job.jd_blob_path || job.jd_filename || job.jd_file_name || job.has_jd || aggregate.jd_raw_text || aggregate.jd_blob_path || aggregate.jd_filename || aggregate.jd_file_name || aggregate.has_jd)

    if (job.status === 'published' && !hasApplicants) return [{ ...job, attention: 'No applicants yet', attentionType: 'published' }]
    if (job.status === 'draft' && !hasJd) return [{ ...job, attention: 'Add a job description', attentionType: 'draft' }]
    return []
  })

  const checklistItems = useMemo(() => {
    if (Array.isArray(onboarding)) return onboarding

    if (onboarding && typeof onboarding === 'object') {
      return Object.entries(onboarding).map(([key, value]) =>
        typeof value === 'object'
          ? { key, ...value }
          : { key, label: formatEnumLabel(key), completed: Boolean(value) }
      )
    }

    return [
      { key: 'profile', label: 'Complete your profile', completed: Boolean(user?.name || user?.full_name) },
      { key: 'resume', label: 'Upload a resume', completed: resumes.length > 0 },
    ]
  }, [onboarding, resumes.length, user?.full_name, user?.name])

  const isDone = (item) => Boolean(item.completed ?? item.done ?? item.is_complete)
  const doneCount = checklistItems.filter(isDone).length
  const NEXT_STEPS = {
    complete_profile: { title: 'Complete your profile', detail: 'Add your name and phone number so recruiters can reach you.', to: '/profile', cta: 'Open profile' },
    profile: { title: 'Complete your profile', detail: 'Add your name and phone number so recruiters can reach you.', to: '/profile', cta: 'Open profile' },
    upload_resume: { title: 'Upload your resume', detail: 'Add a PDF or DOCX resume so you can apply to jobs.', to: '/profile', cta: 'Upload resume' },
    resume: { title: 'Upload your resume', detail: 'Add a PDF or DOCX resume so you can apply to jobs.', to: '/profile', cta: 'Upload resume' },
    apply_to_job: { title: 'Apply to your first job', detail: 'Your resume is ready. Browse open roles and apply.', to: '/jobs', cta: 'Browse jobs' },
  }
  const pendingItem = checklistItems.find((item) => !isDone(item))
  const nextStep = pendingItem ? NEXT_STEPS[pendingItem.key ?? pendingItem.id] : null

  if (loading && !data) return <div className="flex justify-center py-24"><Spinner size="lg" label="Loading overview" /></div>

  return <div className="mx-auto max-w-360 px-8 py-8">
    <PageHeader eyebrow="TalentMatch workspace" title={`Good ${greetingPeriod}, ${profileName ? profileName.split(/\s+/)[0] : (ROLE_LABELS[user?.role] ?? 'Member').toUpperCase()}`} description="A clear view of the work that needs your attention today." action={<Button variant="secondary" onClick={load} disabled={loading}>Refresh overview</Button>} />
    {error && <div role="alert" className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">{error} <button className="ml-2 font-semibold underline" onClick={load}>Retry</button></div>}

    {applicant && nextStep && <div className="mb-6 flex items-center justify-between gap-6 rounded-2xl border border-indigo-200 bg-indigo-50 px-6 py-5 dark:border-indigo-900 dark:bg-indigo-950/60"><div><p className="text-xs font-semibold uppercase tracking-[0.15em] text-indigo-700 dark:text-indigo-300">Next step · {doneCount} of {checklistItems.length} done</p><p className="mt-1 font-semibold text-indigo-950 dark:text-indigo-100">{nextStep.title}</p><p className="mt-1 text-sm text-indigo-800/80 dark:text-indigo-200/80">{nextStep.detail}</p></div><Button onClick={() => navigate(nextStep.to)}>{nextStep.cta}</Button></div>}

    {applicant && <>
      <div className="grid grid-cols-4 gap-4">
        <Metric label="Resume status" value={formatEnumLabel(String(resumeStatus))} detail={resumes[0]?.original_filename || 'A resume is needed to apply'} />
        <Metric label="Applications" value={count(applicationCounts)} detail="Across your current application statuses" />
        <Metric label="Upcoming interviews" value={upcoming.length} detail="Scheduled conversations" />
        <Metric label="Checklist" value={`${checklistItems.filter((item) => item.completed ?? item.done ?? item.is_complete).length}/${checklistItems.length}`} detail="Profile readiness" />
      </div>
      <div className="mt-6 grid grid-cols-2 gap-6">
        <Section title="Application status"><div className="grid grid-cols-2 gap-3">{Object.entries(applicationCounts).map(([status, value]) => <div key={status} className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3 dark:bg-slate-800/70"><span className="text-sm text-slate-600 dark:text-slate-300">{formatEnumLabel(status)}</span><span className="text-lg font-semibold tabular-nums text-slate-900 dark:text-slate-100">{count(value)}</span></div>)}</div>{!Object.keys(applicationCounts).length && <p className="text-sm text-slate-500">Your application status counts will appear here.</p>}</Section>
        <Section title="Get ready to apply"><div className="space-y-3">{checklistItems.map((item, index) => { const done = item.completed ?? item.done ?? item.is_complete; return <div key={item.id ?? item.key ?? index} className="flex items-center gap-3"><span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${done ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-300' : 'bg-slate-100 text-slate-500 dark:bg-slate-800'}`}>{done ? '✓' : index + 1}</span><span className={`text-sm ${done ? 'text-slate-500 line-through' : 'text-slate-800 dark:text-slate-100'}`}>{item.label ?? item.title ?? formatEnumLabel(item.key ?? item.name ?? 'Checklist item')}</span></div> })}<Link to="/profile" className="mt-2 inline-block text-sm font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Review profile →</Link></div></Section>
        <Section title="Upcoming interviews" action={<Link to="/jobs/applied" className="text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Applied jobs →</Link>}><SimpleRows items={upcoming} empty="No upcoming interviews are scheduled yet." render={(item) => <div className="flex items-center justify-between gap-4"><div><p className="font-medium text-slate-800 dark:text-slate-100">{item.job_title ?? item.title ?? item.company ?? 'Interview'}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.interview_at ? new Date(item.interview_at).toLocaleString() : item.scheduled_at ? new Date(item.scheduled_at).toLocaleString() : 'Time to be confirmed'}</p></div><div className="flex items-center gap-3">{(item.interview_at ?? item.scheduled_at) && <Button variant="subtle" size="sm" onClick={() => downloadInterviewIcs({ title: `Interview: ${item.job_title ?? 'TalentMatch'}`, description: 'Interview scheduled via TalentMatch', start: item.interview_at ?? item.scheduled_at })}>Add to calendar</Button>}<StatusBadge status="interview_scheduled" /></div></div>} /></Section>
        <Section title="Recent applications" action={<Link to="/jobs/applied" className="text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">View all →</Link>}><SimpleRows items={recentApplications} empty="Your recent applications will appear here." render={(item) => <div className="flex items-center justify-between gap-4"><div><p className="font-medium text-slate-800 dark:text-slate-100">{item.job_title ?? item.title ?? 'Application'}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.applied_at ? `Applied ${new Date(item.applied_at).toLocaleDateString()}` : item.company ?? ''}</p></div><StatusBadge status={item.status ?? 'applied'} /></div>} /></Section>
        <div className="col-span-2"><Section title="New opportunities" action={<Link to="/jobs" className="text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Browse jobs →</Link>}><SimpleRows items={newestJobs.slice(0, 5)} empty="No new jobs are available right now." render={(item) => <button onClick={() => navigate('/jobs')} className="flex w-full items-center justify-between gap-4 text-left"><div><p className="font-medium text-slate-800 dark:text-slate-100">{item.title ?? item.job_title}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{[item.company, item.location, item.employment_type].filter(Boolean).join(' · ')}</p></div>{appliedJobIds.has(String(item.id)) ? <StatusBadge status="applied">Applied</StatusBadge> : <span className="text-xs font-semibold text-indigo-700 dark:text-indigo-300">View jobs →</span>}</button>} /></Section></div>
      </div>
    </>}

    {recruiter && <>
      <div className="mb-6 grid grid-cols-4 gap-4">
        {[
          ['New applicants', quickActions.new_applicants, 'Waiting for a first look'],
          ['Still scoring', quickActions.still_scoring, 'AI matching in progress'],
          ['Draft jobs', quickActions.draft_jobs, 'Finish and publish'],
          ['Upcoming interviews', quickActions.upcoming_interviews, 'Scheduled ahead'],
        ].map(([label, value, detail]) => <Link key={label} to="/jobs/mine" className="rounded-2xl border border-slate-200/80 bg-white/90 p-5 shadow-sm transition hover:border-indigo-300 hover:shadow dark:border-slate-800 dark:bg-slate-900/80 dark:hover:border-indigo-700"><p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500 dark:text-slate-400">{label}</p><p className="mt-2 font-display text-4xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{value ?? '—'}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{detail}</p></Link>)}
      </div>
      <div className="mb-6 rounded-2xl border border-slate-200/80 bg-[#fbfaf7]/95 p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/90">
        <div className="mb-5 flex items-center justify-between gap-4"><div><h2 className="font-display text-2xl font-semibold text-slate-900 dark:text-slate-100">Hiring funnel</h2><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Application volume by current stage across your jobs.</p></div><StatusBadge status="active">{recruiterJobCount ?? ownJobs.length} jobs</StatusBadge></div>
        <div className="grid grid-cols-5 gap-4">
          {[
            ['Applied', funnelCounts?.applied],
            ['Reviewing', funnelCounts?.reviewing],
            ['Shortlisted', funnelCounts?.shortlisted],
            ['Interview', funnelCounts?.interview],
            ['Hired', funnelCounts?.hired],
          ].map(([label, value], index, stages) => {
            const max = Math.max(1, ...stages.map((stage) => Number(stage[1] ?? 0)))
            const colors = ['bg-slate-400', 'bg-indigo-400', 'bg-violet-500', 'bg-amber-500', 'bg-emerald-500']
            return <div key={label} className="rounded-xl border border-slate-200/80 bg-white p-4 dark:border-slate-800 dark:bg-slate-950/60"><div className="flex items-baseline justify-between gap-2"><span className="text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</span><span className="font-display text-3xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{value ?? '—'}</span></div><div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"><div className={`h-full rounded-full ${colors[index]}`} style={{ width: `${Math.min(100, Number(value ?? 0) / max * 100)}%` }} /></div></div>
          })}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-6">
        <Section title="Interviews this week" action={<Button variant="subtle" size="sm" onClick={() => navigate('/jobs/mine')}>Manage jobs →</Button>}>
          <SimpleRows items={interviewsThisWeek.slice(0, 8)} empty="No interviews are scheduled for the next seven days." render={(item) => <div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate font-medium text-slate-800 dark:text-slate-100">{item.applicant_name ?? item.candidate_name ?? item.job_title ?? 'Interview'}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.job_title ? `${item.job_title} · ` : ''}{new Date(item.interview_at ?? item.scheduled_at).toLocaleString()}</p></div><StatusBadge status="interview_scheduled">Interview</StatusBadge></div>} />
        </Section>
        <Section title="Needs attention" action={<Button variant="subtle" size="sm" onClick={() => navigate('/jobs/mine')}>Open My jobs →</Button>}>
          <SimpleRows items={attentionJobs.slice(0, 8)} empty="No jobs need attention right now." render={(job) => <div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate font-medium text-slate-800 dark:text-slate-100">{job.title ?? 'Untitled job'}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{job.attention}</p></div><StatusBadge status={job.attentionType === 'draft' ? 'draft' : 'pending'}>{job.attentionType === 'draft' ? 'Draft' : 'Published'}</StatusBadge></div>} />
        </Section>
      </div>
      <div className="mt-6"><Section title="My jobs" action={<Button size="sm" onClick={() => navigate('/jobs/mine')}>Manage jobs</Button>}><SimpleRows items={ownJobs.slice(0, 8)} empty="Create your first job to begin receiving candidates." render={(job) => <div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate font-medium text-slate-800 dark:text-slate-100">{job.title}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{count(job.applicant_count ?? job.applicants_count)} applicants · {count(job.new_count ?? job.new_applicants)} new · {count(job.still_scoring_count ?? job.scoring_count)} scoring</p></div><Link to={`/jobs/${job.id}/applicants`} className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-indigo-200/80 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 shadow-sm transition hover:border-indigo-300 hover:bg-indigo-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 dark:border-indigo-800 dark:bg-indigo-950/60 dark:text-indigo-300 dark:hover:border-indigo-700 dark:hover:bg-indigo-900/70 dark:focus-visible:ring-offset-slate-900">Applicants <span aria-hidden="true">→</span></Link></div>} /></Section></div>
    </>}

    {admin && <>
      <div className="grid grid-cols-4 gap-4"><Metric label="Recruiter requests" value={pendingRequests} detail="Waiting for review" tone="indigo" /><Metric label="Unset LLM tasks" value={unsetTaskCount} detail="Model configuration gaps" tone={unsetTaskCount ? 'red' : 'indigo'} /><Metric label="Queue depth" value={healthQueueDepth ?? queueDepth ?? '—'} detail="Background work waiting" /><Metric label="Quota usage" value={(healthQuota ?? quota) && typeof (healthQuota ?? quota) === 'object' ? `${(healthQuota ?? quota).used ?? (healthQuota ?? quota).current ?? 0}${(healthQuota ?? quota).limit ? ` / ${(healthQuota ?? quota).limit}` : ''}` : healthQuota ?? quota ?? '—'} detail="Current quota window" /></div>
      <div className={`mt-6 grid gap-6 ${isSuperuser ? 'grid-cols-2' : 'grid-cols-1'}`}>
        <Section title="Recruiter requests" action={<Link to="/users?pending=true" className="text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Review all →</Link>}><SimpleRows items={pendingRecruiters} empty="No recruiter requests are waiting." render={(item) => <div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate font-medium text-slate-800 dark:text-slate-100">{item.full_name || item.email}</p><p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400">{item.full_name ? `${item.email} · ` : ''}{item.created_at ? `Requested ${new Date(item.created_at).toLocaleDateString()}` : 'Requested recruiter access'}</p></div><Button size="sm" variant="secondary" onClick={() => navigate('/users?pending=true')}>Review</Button></div>} /></Section>
        {isSuperuser && <Section title="Superuser controls"><div className="space-y-3 text-sm"><p className="text-slate-600 dark:text-slate-300">Actions only the superuser can take.</p><Link to="/users" className="block rounded-xl bg-slate-50 px-4 py-3 font-semibold text-indigo-700 hover:bg-indigo-50 dark:bg-slate-800/70 dark:text-indigo-300 dark:hover:bg-indigo-950/60">Promote or demote admins →</Link><Link to="/users" className="block rounded-xl bg-slate-50 px-4 py-3 font-semibold text-indigo-700 hover:bg-indigo-50 dark:bg-slate-800/70 dark:text-indigo-300 dark:hover:bg-indigo-950/60">Transfer the superuser role →</Link><Link to="/audit" className="block rounded-xl bg-slate-50 px-4 py-3 font-semibold text-indigo-700 hover:bg-indigo-50 dark:bg-slate-800/70 dark:text-indigo-300 dark:hover:bg-indigo-950/60">Review the full audit feed →</Link></div></Section>}
      </div>
      <div className="mt-6 grid grid-cols-2 gap-6"><Section title="LLM configuration" action={<Link to="/admin/llm" className="text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Open settings →</Link>}><SimpleRows items={unsetTasks} empty="All task models appear to be configured." render={(task) => <div className="flex items-center justify-between"><span className="text-sm text-slate-700 dark:text-slate-200">{typeof task === 'string' ? formatEnumLabel(task) : formatEnumLabel(task.task ?? task.name ?? 'Task')}</span><StatusBadge status="missing" tone="danger">Model unset</StatusBadge></div>} /></Section>
        <Section title="Recent audit activity" action={<Link to="/audit" className="text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">View audit feed →</Link>}><SimpleRows items={auditActivity.slice(0, 8)} empty="No recent audit activity." render={(entry) => <div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate font-medium text-slate-800 dark:text-slate-100">{entry.resource_label ?? entry.resource_type ?? 'Activity'} · {entry.action}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{entry.actor_email ?? entry.actor_id ?? 'System'}{entry.created_at ? ` · ${new Date(entry.created_at).toLocaleString()}` : ''}</p></div><StatusBadge status={entry.action} /></div>} /></Section></div>
      <div className="mt-6"><Section title="System status"><div className="grid grid-cols-3 gap-4"><div><p className="text-xs text-slate-500">Queue depth</p><p className="mt-1 text-xl font-semibold text-slate-900 dark:text-slate-100">{healthQueueDepth ?? queueDepth ?? 'Not reported'}</p></div><div><p className="text-xs text-slate-500">Quota window</p><p className="mt-1 text-xl font-semibold text-slate-900 dark:text-slate-100">{(healthQuota ?? quota) ? (typeof (healthQuota ?? quota) === 'object' ? JSON.stringify(healthQuota ?? quota) : healthQuota ?? quota) : 'Not reported'}</p></div><div><Link to="/users" className="text-sm font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Manage users and recruiter requests →</Link></div></div></Section></div>
      <div className="mt-6 grid grid-cols-3 gap-6"><Section title="Runtime health"><div className="space-y-3"><div className="flex items-center justify-between"><span className="text-sm text-slate-600 dark:text-slate-300">Redis</span><StatusBadge status={String(redisStatus ?? 'unknown')}>{typeof redisStatus === 'object' ? (redisStatus.status ?? 'Unknown') : String(redisStatus ?? 'Unknown')}</StatusBadge></div><div className="flex items-center justify-between"><span className="text-sm text-slate-600 dark:text-slate-300">Stuck rows</span><span className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">{stuckRows.length || count(read(health, 'stuck_row_count'))}</span></div><p className="text-xs text-slate-500 dark:text-slate-400">Metrics refresh every minute and when this window regains focus.</p></div></Section><Section title="LLM probes"><SimpleRows items={probes} empty="No recent LLM probe results were reported." render={(probe) => <div className="flex items-center justify-between gap-3"><span className="text-sm text-slate-700 dark:text-slate-200">{formatEnumLabel(probe.task ?? probe.name ?? 'LLM task')}</span><StatusBadge status={probe.ok ? 'success' : probe.status ?? 'unknown'}>{probe.ok === true ? 'Passed' : probe.ok === false ? 'Failed' : probe.status ?? 'Unknown'}</StatusBadge></div>} /></Section><Section title="Stuck work items"><SimpleRows items={stuckRows.slice(0, 6)} empty="No stuck queue items reported." render={(item) => <div><p className="text-sm font-medium text-slate-800 dark:text-slate-100">{item.task ?? item.type ?? item.id ?? 'Background task'}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.reason ?? item.status ?? item.updated_at ?? ''}</p></div>} /></Section></div>
    </>}
  </div>
}