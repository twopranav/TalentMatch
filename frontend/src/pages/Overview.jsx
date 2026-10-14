import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { fetchOverview, fetchAdminHealthMetrics } from '../api/overview'
import { useResumes } from '../hooks/useResumes'
import { formatEnumLabel } from '../utils/format'
import Spinner from '../components/ui/Spinner'
import StatusBadge from '../components/ui/StatusBadge'
import Button from '../components/ui/Button'

function getGreetingPeriod(date = new Date()) {
  const hour = date.getHours()
  if (hour < 12) return 'Morning'
  if (hour < 18) return 'Afternoon'
  return 'Evening'
}

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
function count(value) { if (typeof value === 'number') return value; if (Array.isArray(value)) return value.length; if (value && typeof value === 'object') return Object.values(value).reduce((sum, item) => sum + (Number(item) || 0), 0); return Number(value ?? 0) }
function Metric({ label, value, detail, tone = 'indigo' }) {
  const accent = tone === 'red' ? 'border-red-300/70 dark:border-red-900' : 'border-indigo-300/70 dark:border-indigo-800'
  return <div className={`rounded-2xl border ${accent} bg-white/90 p-5 shadow-sm dark:bg-slate-900/80`}><p className="text-xs font-semibold uppercase tracking-[0.15em] text-slate-500 dark:text-slate-400">{label}</p><p className="mt-2 font-display text-4xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{value ?? '—'}</p>{detail && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{detail}</p>}</div>
}
function Section({ title, action, children }) {
  return <section className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/90 shadow-sm dark:border-slate-800 dark:bg-slate-900/80"><div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-800"><h2 className="font-display text-2xl font-semibold text-slate-900 dark:text-slate-100">{title}</h2>{action}</div><div className="p-5">{children}</div></section>
}
function SimpleRows({ items, empty, render }) {
  if (!items.length) return <p className="py-3 text-sm text-slate-500 dark:text-slate-400">{empty}</p>
  return <div className="divide-y divide-slate-100 dark:divide-slate-800">{items.map((item, index) => <div key={item.id ?? item.job_id ?? item.application_id ?? index} className="py-3 first:pt-0 last:pb-0">{render(item)}</div>)}</div>
}

export default function Overview() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [greetingPeriod, setGreetingPeriod] = useState(() => getGreetingPeriod())
  const { resumes } = useResumes({ enabled: user?.role === 'user' })
  const applicant = user?.role === 'user'
  const recruiter = user?.role === 'recruiter'
  const admin = ['admin', 'superuser'].includes(user?.role)
  const load = useCallback(() => {
    setLoading(true); setError('')
    fetchOverview().then(setData).catch(() => setError('Could not load the overview. Please try again.')).finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])
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
    return () => { window.clearInterval(interval); window.removeEventListener('focus', refreshHealth) }
  }, [admin])

  const candidate = read(data, 'applicant', 'candidate', 'data.applicant') ?? data ?? {}
  const recruiterData = read(data, 'recruiter', 'data.recruiter') ?? data ?? {}
  const adminData = read(data, 'admin', 'data.admin') ?? data ?? {}
  const ownJobs = rows(read(recruiterData, 'jobs', 'own_jobs', 'my_jobs'))
  const upcoming = rows(read(applicant ? candidate : recruiterData, 'upcoming_interviews', 'interviews.upcoming'))
  const recentApplications = rows(read(candidate, 'recent_applications', 'applications.recent'))
  const newestJobs = rows(read(candidate, 'newest_jobs', 'jobs.newest', 'latest_jobs'))
  const applicationCounts = read(candidate, 'application_status_counts', 'applications_by_status', 'application_counts') ?? {}
  const onboarding = read(candidate, 'onboarding_checklist', 'onboarding', 'checklist')
  const resumeStatus = read(candidate, 'resume_status') ?? (resumes.length ? (resumes[0]?.status ?? 'uploaded') : 'missing')
  const pendingRequestRaw = read(adminData, 'pending_recruiter_requests', 'pending_recruiter_requests_count', 'recruiter_requests_pending') ?? 0
  const pendingRequests = count(pendingRequestRaw)
  const unsetTasks = rows(read(adminData, 'unset_llm_tasks', 'llm_tasks_unset', 'unset_models'))
  const unsetTaskCount = Math.max(unsetTasks.length, Number(read(adminData, 'unset_llm_tasks_count', 'llm_tasks_unset_count', 'unset_models_count') ?? 0))
  const healthQueueDepth = read(health, 'queue_depth', 'system_queue_depth', 'queue.depth')
  const healthQuota = read(health, 'quota_usage', 'quota')
  const stuckRows = rows(read(health, 'stuck_rows', 'stuck_tasks', 'stuck_records'))
  const redisStatus = read(health, 'redis_status', 'redis.status', 'redis')
  const probes = rows(read(health, 'llm_tasks', 'task_results', 'last_probe_results', 'probes'))
  const auditActivity = rows(read(adminData, 'recent_audit_activity', 'recent_audit', 'audit_activity'))
  const quota = read(adminData, 'quota_usage', 'quota')
  const queueDepth = read(adminData, 'system_queue_depth', 'queue_depth', 'queue.depth')

  const checklistItems = useMemo(() => {
    if (Array.isArray(onboarding)) return onboarding
    if (onboarding && typeof onboarding === 'object') return Object.entries(onboarding).map(([key, value]) => typeof value === 'object' ? { key, ...value } : { key, label: formatEnumLabel(key), completed: Boolean(value) })
    return [
      { key: 'profile', label: 'Complete your profile', completed: Boolean(user?.name || user?.full_name) },
      { key: 'resume', label: 'Upload a resume', completed: resumes.length > 0 },
    ]
  }, [onboarding, resumes.length, user?.full_name, user?.name])

  if (loading && !data) return <div className="flex justify-center py-24"><Spinner size="lg" label="Loading overview" /></div>

  return <div className="mx-auto max-w-360 px-8 py-8">
    <div className="mb-8 flex items-end justify-between gap-6">
      <div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.22em] text-indigo-600 dark:text-indigo-300">TalentMatch workspace</p><h1 className="text-5xl font-semibold text-slate-900 dark:text-slate-100">Good {greetingPeriod}{user?.name ? `, ${user.name.split(' ')[0]}` : ''}</h1><p className="mt-3 max-w-2xl text-sm text-slate-500 dark:text-slate-400">A clear view of the work that needs your attention today.</p></div>
      <Button variant="secondary" onClick={load} disabled={loading}>Refresh overview</Button>
    </div>
    {error && <div role="alert" className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">{error} <button className="ml-2 font-semibold underline" onClick={load}>Retry</button></div>}

    {applicant && resumes.length === 0 && <div className="mb-6 flex items-center justify-between gap-6 rounded-2xl border border-indigo-200 bg-indigo-50 px-6 py-5 dark:border-indigo-900 dark:bg-indigo-950/60"><div><p className="font-semibold text-indigo-950 dark:text-indigo-100">Upload your resume to start applying</p><p className="mt-1 text-sm text-indigo-800/80 dark:text-indigo-200/80">Add a PDF or DOCX resume to make your applications available to recruiters.</p></div><Button onClick={() => navigate('/profile')}>Upload resume</Button></div>}

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
        <Section title="Upcoming interviews" action={<Link to="/jobs/applied" className="text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Applied jobs →</Link>}><SimpleRows items={upcoming} empty="No upcoming interviews are scheduled yet." render={(item) => <div className="flex items-center justify-between gap-4"><div><p className="font-medium text-slate-800 dark:text-slate-100">{item.job_title ?? item.title ?? item.company ?? 'Interview'}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.interview_at ? new Date(item.interview_at).toLocaleString() : item.scheduled_at ? new Date(item.scheduled_at).toLocaleString() : 'Time to be confirmed'}</p></div><StatusBadge status="interview_scheduled" /></div>} /></Section>
        <Section title="Recent applications" action={<Link to="/jobs/applied" className="text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">View all →</Link>}><SimpleRows items={recentApplications} empty="Your recent applications will appear here." render={(item) => <div className="flex items-center justify-between gap-4"><div><p className="font-medium text-slate-800 dark:text-slate-100">{item.job_title ?? item.title ?? 'Application'}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.applied_at ? `Applied ${new Date(item.applied_at).toLocaleDateString()}` : item.company ?? ''}</p></div><StatusBadge status={item.status ?? 'applied'} /></div>} /></Section>
        <div className="col-span-2"><Section title="New opportunities" action={<Link to="/jobs" className="text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Browse jobs →</Link>}><SimpleRows items={newestJobs.slice(0, 5)} empty="No new jobs are available right now." render={(item) => <button onClick={() => navigate('/jobs')} className="flex w-full items-center justify-between gap-4 text-left"><div><p className="font-medium text-slate-800 dark:text-slate-100">{item.title ?? item.job_title}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{[item.company, item.location, item.employment_type].filter(Boolean).join(' · ')}</p></div><span className="text-xs font-semibold text-indigo-700 dark:text-indigo-300">View jobs →</span></button>} /></Section></div>
      </div>
    </>}

    {recruiter && <>
      <div className="grid grid-cols-4 gap-4"><Metric label="My jobs" value={ownJobs.length} detail="Jobs you own" /><Metric label="New applicants" value={ownJobs.reduce((n, job) => n + count(job.new_count ?? job.new_applicants), 0)} /><Metric label="Still scoring" value={ownJobs.reduce((n, job) => n + count(job.still_scoring_count ?? job.scoring_count), 0)} /><Metric label="Shortlisted" value={ownJobs.reduce((n, job) => n + count(job.shortlisted_count ?? job.shortlisted), 0)} /></div>
      <div className="mt-6 grid grid-cols-2 gap-6"><Section title="My jobs" action={<Button size="sm" onClick={() => navigate('/jobs/mine')}>Manage jobs</Button>}><SimpleRows items={ownJobs.slice(0, 8)} empty="Create your first job to begin receiving candidates." render={(job) => <div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate font-medium text-slate-800 dark:text-slate-100">{job.title}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{count(job.applicant_count ?? job.applicants_count)} applicants · {count(job.new_count ?? job.new_applicants)} new · {count(job.still_scoring_count ?? job.scoring_count)} scoring</p></div><Link to={`/jobs/${job.id}/applicants`} className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-indigo-200/80 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 shadow-sm transition hover:border-indigo-300 hover:bg-indigo-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-offset-2 dark:border-indigo-800 dark:bg-indigo-950/60 dark:text-indigo-300 dark:hover:border-indigo-700 dark:hover:bg-indigo-900/70 dark:focus-visible:ring-offset-slate-900">Applicants <span aria-hidden="true">→</span></Link></div>} /></Section>
        <Section title="Upcoming interviews"><SimpleRows items={upcoming} empty="No upcoming interviews across your jobs." render={(item) => <div className="flex items-center justify-between gap-4"><div><p className="font-medium text-slate-800 dark:text-slate-100">{item.applicant_name ?? item.candidate_name ?? 'Candidate'} · {item.job_title ?? 'Job'}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.interview_at ? new Date(item.interview_at).toLocaleString() : 'Time to be confirmed'}</p></div><StatusBadge status="interview_scheduled" /></div>} /></Section></div>
      <div className="mt-6 grid grid-cols-3 gap-4"><Metric label="Jobs with applicants" value={ownJobs.filter((job) => count(job.applicant_count ?? job.applicants_count) > 0).length} /><Metric label="Needs review" value={ownJobs.reduce((n, job) => n + count(job.new_count ?? job.new_applicants), 0)} detail="New applications" /><Metric label="Quick actions" value={count(read(recruiterData, 'quick_action_metrics', 'quick_actions'))} detail="Actions waiting for attention" /></div>
    </>}

    {admin && <>
      <div className="grid grid-cols-4 gap-4"><Metric label="Recruiter requests" value={pendingRequests} detail="Waiting for review" tone="indigo" /><Metric label="Unset LLM tasks" value={unsetTaskCount} detail="Model configuration gaps" tone={unsetTaskCount ? 'red' : 'indigo'} /><Metric label="Queue depth" value={healthQueueDepth ?? queueDepth ?? '—'} detail="Background work waiting" /><Metric label="Quota usage" value={(healthQuota ?? quota) && typeof (healthQuota ?? quota) === 'object' ? `${(healthQuota ?? quota).used ?? (healthQuota ?? quota).current ?? 0}${(healthQuota ?? quota).limit ? ` / ${(healthQuota ?? quota).limit}` : ''}` : healthQuota ?? quota ?? '—'} detail="Current quota window" /></div>
      <div className="mt-6 grid grid-cols-2 gap-6"><Section title="LLM configuration" action={<Link to="/admin/llm" className="text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Open settings →</Link>}><SimpleRows items={unsetTasks} empty="All task models appear to be configured." render={(task) => <div className="flex items-center justify-between"><span className="text-sm text-slate-700 dark:text-slate-200">{typeof task === 'string' ? formatEnumLabel(task) : formatEnumLabel(task.task ?? task.name ?? 'Task')}</span><StatusBadge status="missing" tone="danger">Model unset</StatusBadge></div>} /></Section>
        <Section title="Recent audit activity" action={<Link to="/audit" className="text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">View audit feed →</Link>}><SimpleRows items={auditActivity.slice(0, 8)} empty="No recent audit activity." render={(entry) => <div className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate font-medium text-slate-800 dark:text-slate-100">{entry.resource_label ?? entry.resource_type ?? 'Activity'} · {entry.action}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{entry.actor_email ?? entry.actor_id ?? 'System'}{entry.created_at ? ` · ${new Date(entry.created_at).toLocaleString()}` : ''}</p></div><StatusBadge status={entry.action} /></div>} /></Section></div>
      <div className="mt-6"><Section title="System status"><div className="grid grid-cols-3 gap-4"><div><p className="text-xs text-slate-500">Queue depth</p><p className="mt-1 text-xl font-semibold text-slate-900 dark:text-slate-100">{healthQueueDepth ?? queueDepth ?? 'Not reported'}</p></div><div><p className="text-xs text-slate-500">Quota window</p><p className="mt-1 text-xl font-semibold text-slate-900 dark:text-slate-100">{(healthQuota ?? quota) ? (typeof (healthQuota ?? quota) === 'object' ? JSON.stringify(healthQuota ?? quota) : healthQuota ?? quota) : 'Not reported'}</p></div><div><Link to="/users" className="text-sm font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Manage users and recruiter requests →</Link></div></div></Section></div>
      <div className="mt-6 grid grid-cols-3 gap-6"><Section title="Runtime health"><div className="space-y-3"><div className="flex items-center justify-between"><span className="text-sm text-slate-600 dark:text-slate-300">Redis</span><StatusBadge status={String(redisStatus ?? 'unknown')}>{typeof redisStatus === 'object' ? (redisStatus.status ?? 'Unknown') : String(redisStatus ?? 'Unknown')}</StatusBadge></div><div className="flex items-center justify-between"><span className="text-sm text-slate-600 dark:text-slate-300">Stuck rows</span><span className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">{stuckRows.length || count(read(health, 'stuck_row_count'))}</span></div><p className="text-xs text-slate-500 dark:text-slate-400">Metrics refresh every minute and when this window regains focus.</p></div></Section><Section title="LLM probes"><SimpleRows items={probes} empty="No recent LLM probe results were reported." render={(probe) => <div className="flex items-center justify-between gap-3"><span className="text-sm text-slate-700 dark:text-slate-200">{formatEnumLabel(probe.task ?? probe.name ?? 'LLM task')}</span><StatusBadge status={probe.ok ? 'success' : probe.status ?? 'unknown'}>{probe.ok === true ? 'Passed' : probe.ok === false ? 'Failed' : probe.status ?? 'Unknown'}</StatusBadge></div>} /></Section><Section title="Stuck work items"><SimpleRows items={stuckRows.slice(0, 6)} empty="No stuck queue items reported." render={(item) => <div><p className="text-sm font-medium text-slate-800 dark:text-slate-100">{item.task ?? item.type ?? item.id ?? 'Background task'}</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.reason ?? item.status ?? item.updated_at ?? ''}</p></div>} /></Section></div>
    </>}
  </div>
}
