import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useJobs } from '../hooks/useJobs'
import { updateJob } from '../api/jobs'
import { fetchOverview } from '../api/overview'
import JobFormDrawer from '../components/jobs/JobFormDrawer'
import JDUploadModal from '../components/jobs/JDUploadModal'
import Spinner from '../components/ui/Spinner'
import Pagination from '../components/ui/Pagination'
import ActionMenu from '../components/ui/ActionMenu'
import Button from '../components/ui/Button'
import StatusBadge from '../components/ui/StatusBadge'
import { useToast } from '../components/ui/Toast'
import { formatEnumLabel, getErrorMessage } from '../utils/format'

const PAGE_SIZE = 25

export default function MyJobs() {
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [searchDraft, setSearchDraft] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const { jobs, total, loading, error, refetch } = useJobs({ created_by: 'me', q: query || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE })
  const [editingJob, setEditingJob] = useState(null)
  const [formOpen, setFormOpen] = useState(false)
  const [uploadJob, setUploadJob] = useState(null)
  const [busyJobId, setBusyJobId] = useState(null)
  const [overviewJobs, setOverviewJobs] = useState({})
  const refreshOverview = useCallback(async () => {
    try {
      const response = await fetchOverview()
      const payload = response?.data?.data ?? response?.data ?? response
      // Recruiter overview responses use a top-level jobs array; accept the
      // nested variants as well for older backend deployments.
      const own = payload?.jobs ?? payload?.recruiter?.jobs ?? payload?.own_jobs ?? payload?.my_jobs ?? []
      const rows = Array.isArray(own)
        ? own
        : own && typeof own === 'object'
          ? Object.entries(own).map(([id, job]) => job && typeof job === 'object' ? { ...job, id: job.id ?? job.job_id ?? id } : null).filter(Boolean)
          : []
      setOverviewJobs(Object.fromEntries(rows.filter((job) => job?.id != null || job?.job_id != null).map((job) => [String(job.id ?? job.job_id), job])))
    } catch {
      // Retain the last successful values if the overview endpoint is temporarily unavailable.
    }
  }, [])
  useEffect(() => {
    refreshOverview()
    const refreshWhenVisible = () => { if (!document.hidden) refreshOverview() }
    window.addEventListener('focus', refreshOverview)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    const interval = window.setInterval(refreshOverview, 60000)
    return () => {
      window.removeEventListener('focus', refreshOverview)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
      window.clearInterval(interval)
    }
  }, [refreshOverview])
  const displayJobs = jobs.map((job) => {
    const stats = overviewJobs[String(job.id)] ?? overviewJobs[String(job.job_id)] ?? {}
    return { ...job, applicant_count: job.applicant_count ?? job.applicants_count ?? stats.applicant_count ?? stats.applicants_count ?? stats.total_applicants ?? stats.applications_count, new_count: job.new_count ?? job.new_applicants ?? stats.new_count ?? stats.new_applicants ?? stats.new_application_count, still_scoring_count: job.still_scoring_count ?? job.scoring_count ?? stats.still_scoring_count ?? stats.scoring_count ?? stats.still_scoring, shortlisted_count: job.shortlisted_count ?? stats.shortlisted_count ?? stats.shortlisted ?? stats.shortlisted_applications }
  })
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const publishedCount = jobs.filter((job) => job.status === 'published').length
  const jobsWithJD = jobs.filter((job) => Boolean(job.jd_raw_text || job.jd_blob_path || job.jd_filename)).length

  const openEdit = (job) => { setEditingJob(job); setFormOpen(true) }
  const setStatus = async (job, status) => {
    setBusyJobId(job.id)
    try { await updateJob(job.id, { status }); showToast(`Job marked ${formatEnumLabel(status).toLowerCase()}.`, 'success'); refetch(); refreshOverview() }
    catch (err) { showToast(getErrorMessage(err, 'Could not update the job status.'), 'error') }
    finally { setBusyJobId(null) }
  }

  return <div className="mx-auto max-w-[1440px] px-8 py-8">
    <div className="mb-7 flex items-end justify-between gap-5"><div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600 dark:text-indigo-300">Recruiter workspace</p><h1 className="text-5xl font-semibold text-slate-900 dark:text-slate-100">My jobs</h1><p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Manage each opening and move applicant reviews forward.</p></div><Button onClick={() => { setEditingJob(null); setFormOpen(true) }}>+ New job</Button></div>
    <section className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><div className="mb-4 flex items-center justify-between"><div><h2 className="font-display text-2xl font-semibold text-slate-900 dark:text-slate-100">Setup checklist</h2><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">A quick path from draft to a ready-to-review role.</p></div><span className="text-xs text-slate-500">{publishedCount} published on this page</span></div><div className="grid grid-cols-3 gap-4"><div className="flex gap-3 rounded-xl bg-slate-50 p-3 dark:bg-slate-800/70"><span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">1</span><div><p className="text-sm font-semibold text-slate-800 dark:text-slate-100">Create a job</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Add a title and role details.</p></div></div><div className="flex gap-3 rounded-xl bg-slate-50 p-3 dark:bg-slate-800/70"><span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${jobsWithJD ? 'bg-emerald-100 text-emerald-800' : 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200'}`}>{jobsWithJD ? '✓' : '2'}</span><div><p className="text-sm font-semibold text-slate-800 dark:text-slate-100">Add a job description</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Help the matching process score candidates.</p></div></div><div className="flex gap-3 rounded-xl bg-slate-50 p-3 dark:bg-slate-800/70"><span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${publishedCount ? 'bg-emerald-100 text-emerald-800' : 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200'}`}>{publishedCount ? '✓' : '3'}</span><div><p className="text-sm font-semibold text-slate-800 dark:text-slate-100">Publish and review</p><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Triage new applications as they arrive.</p></div></div></div></section>
    <div className="mb-3 flex items-baseline gap-2" aria-live="polite"><span className="font-display text-3xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{total}</span><span className="text-sm font-medium text-slate-500 dark:text-slate-400">{total === 1 ? 'job' : 'jobs'}</span></div>
    <form onSubmit={(event) => { event.preventDefault(); setQuery(searchDraft.trim()); setPage(1) }} className="mb-4 flex items-center gap-3 rounded-xl border border-slate-200 bg-[#fbfaf7]/95 p-3 dark:border-slate-800 dark:bg-slate-900"><label htmlFor="my-jobs-search" className="sr-only">Search my jobs</label><input id="my-jobs-search" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="Search your job titles, skills, or locations" className="min-w-0 flex-1 border-0 bg-transparent px-2 py-1.5 text-sm focus:outline-none focus:ring-0 dark:text-slate-100" /><Button type="submit" size="sm" className="h-9 w-10 !px-0" aria-label="Search jobs" title="Search jobs"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg></Button>{query && <Button variant="subtle" size="sm" onClick={() => { setSearchDraft(''); setQuery(''); setPage(1) }}>Clear</Button>}</form>
    {loading && <div className="flex justify-center py-16"><Spinner size="lg" label="Loading your jobs" /></div>}
    {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
    {!loading && !error && jobs.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 px-6 py-16 text-center dark:border-slate-700"><p className="text-sm text-slate-500 dark:text-slate-400">{query ? 'No jobs match this search.' : 'You have not posted any jobs yet. Create a job to get started.'}</p><Button className="mt-4" onClick={() => { setEditingJob(null); setFormOpen(true) }}>Create your first job</Button></div>}
    {!loading && !error && jobs.length > 0 && <div className="overflow-visible rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"><table className="w-full text-left"><thead className="bg-slate-50 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400"><tr><th className="px-5 py-3">Job</th><th className="px-4 py-3">Applicants</th><th className="px-4 py-3">New</th><th className="px-4 py-3">Scoring</th><th className="px-4 py-3">Shortlisted</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Actions</th></tr></thead><tbody>{displayJobs.map((job) => <tr key={job.id} className="border-t border-slate-100 hover:bg-slate-50/70 dark:border-slate-800 dark:hover:bg-slate-800/40"><td className="max-w-lg px-5 py-4"><p className="truncate font-semibold text-slate-900 dark:text-slate-100">{job.title}</p><p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400">{[job.location, formatEnumLabel(job.employment_type), formatEnumLabel(job.remote_type)].filter(Boolean).join(' · ')}</p></td><td className="px-4 py-4 text-sm tabular-nums text-slate-700 dark:text-slate-200">{job.applicant_count ?? job.applicants_count ?? '—'}</td><td className="px-4 py-4 text-sm tabular-nums text-slate-700 dark:text-slate-200">{job.new_count ?? job.new_applicants ?? '—'}</td><td className="px-4 py-4 text-sm tabular-nums text-slate-700 dark:text-slate-200">{job.still_scoring_count ?? job.scoring_count ?? '—'}</td><td className="px-4 py-4 text-sm tabular-nums text-slate-700 dark:text-slate-200">{job.shortlisted_count ?? '—'}</td><td className="px-4 py-4"><StatusBadge status={job.status}>{formatEnumLabel(job.status)}</StatusBadge></td><td className="px-4 py-4"><div className="flex items-center gap-2">{job.status === 'draft' && <Button size="sm" disabled={busyJobId === job.id} onClick={() => setStatus(job, 'published')}>Publish</Button>}{job.status === 'published' && <Button size="sm" variant="secondary" disabled={busyJobId === job.id} onClick={() => setStatus(job, 'closed')}>Close</Button>}<ActionMenu label={`Actions for ${job.title}`} items={[{ label: 'Edit job', onSelect: () => openEdit(job) }, { label: 'Review applicants', onSelect: () => navigate(`/jobs/${job.id}/applicants`) }, { label: 'Upload / replace JD', onSelect: () => setUploadJob(job) }, { label: 'View audit history', onSelect: () => navigate(`/audit?job_id=${job.id}`) }]} /></div></td></tr>)}</tbody></table></div>}
    {!loading && !error && <div className="mt-4 flex items-center justify-between"><p className="text-xs text-slate-500">Showing {total ? (page - 1) * PAGE_SIZE + 1 : 0}–{Math.min(page * PAGE_SIZE, total)} of {total} jobs</p><Pagination page={page} totalPages={totalPages} onPageChange={setPage} disabled={loading} /></div>}
    <JobFormDrawer open={formOpen} onClose={() => setFormOpen(false)} job={editingJob} onSaved={() => { refetch(); refreshOverview() }} />
    <JDUploadModal open={Boolean(uploadJob)} onClose={() => setUploadJob(null)} job={uploadJob} onUploaded={() => { refetch(); refreshOverview() }} />
  </div>
}
