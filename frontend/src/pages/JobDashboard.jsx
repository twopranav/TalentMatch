import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useJobs } from '../hooks/useJobs'
import { useMyApplications } from '../hooks/useApplications'
import { useResumes } from '../hooks/useResumes'
import JobList from '../components/jobs/JobList'
import JobFilterBar from '../components/jobs/JobFilterBar'
import JobFormDrawer from '../components/jobs/JobFormDrawer'
import JDUploadModal from '../components/jobs/JDUploadModal'
import JobDetailsModal from '../components/jobs/JobDetailsModal'
import Pagination from '../components/ui/Pagination'
import { formatEnumLabel, getErrorMessage } from '../utils/format'
import { applyToJob, fetchStageCounts, withdrawApplication } from '../api/applications'
import { useToast } from '../components/ui/Toast'
import Button from '../components/ui/Button'

const STATUS_OPTIONS = ['all', 'draft', 'published', 'closed']
const PAGE_SIZE = 25

export default function JobDashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const [filters, setFilters] = useState({ status: 'all', location: '', department: '', employment_type: '', seniority: '', remote_type: '' })
  const [searchText, setSearchText] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const canManageJobs = ['recruiter', 'admin', 'superuser'].includes(user?.role)
  const canFilterByStatus = user?.role !== 'user'
  const isApplicant = user?.role === 'user'
  const queryFilters = {
    ...filters,
    status: filters.status === 'all' ? undefined : filters.status,
    q: query || undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  }
  const { jobs, total, loading, error, refetch } = useJobs(queryFilters)
  const { applications: myApplications, refetch: refetchMyApplications } = useMyApplications(isApplicant)
  const { resumes } = useResumes({ enabled: isApplicant })
  const [stageCounts, setStageCounts] = useState(null)
  useEffect(() => {
    if (!canFilterByStatus) return
    fetchStageCounts().then(setStageCounts).catch(() => setStageCounts(null))
  }, [canFilterByStatus, jobs])
  const myApplicationsByJob = useMemo(() => {
    const map = {}
    for (const application of myApplications) map[application.job_id] = application
    return map
  }, [myApplications])

  const [selectedJob, setSelectedJob] = useState(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editingJob, setEditingJob] = useState(null)
  const [uploadJob, setUploadJob] = useState(null)
  const [applyingJobId, setApplyingJobId] = useState(null)

  const openCreate = () => { setEditingJob(null); setFormOpen(true) }
  const openEdit = (job) => { setSelectedJob(null); setEditingJob(job); setFormOpen(true) }
  const handleChanged = (updated) => { setSelectedJob(updated); refetch() }
  const handleUploaded = () => refetch()
  const handleApplicationChanged = () => refetchMyApplications()

  const handleApply = async (job) => {
    if (isApplicant && resumes.length === 0) {
      showToast('Upload your resume to start applying.', 'info')
      navigate('/profile')
      return
    }
    setApplyingJobId(job.id)
    try {
      await applyToJob(job.id)
      showToast('Application submitted.', 'success')
      refetchMyApplications()
    } catch (err) { showToast(getErrorMessage(err, 'Could not submit your application.'), 'error') }
    finally { setApplyingJobId(null) }
  }

  const handleWithdraw = async (application) => {
    setApplyingJobId(application.job_id)
    try { await withdrawApplication(application.id); showToast('Application withdrawn.', 'success'); refetchMyApplications() }
    catch { showToast('Could not withdraw your application.', 'error') }
    finally { setApplyingJobId(null) }
  }
  const changeFilters = (next) => { setFilters(next); setPage(1) }
  const applySearch = (event) => { event.preventDefault(); setQuery(searchText.trim()); setPage(1) }
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return <div className="mx-auto max-w-[1440px] px-8 py-8">
    <div className="mb-6 flex items-end justify-between gap-6">
      <div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600 dark:text-indigo-300">Opportunity directory</p><h1 className="text-5xl font-semibold text-slate-900 dark:text-slate-100">{isApplicant ? 'Find your next role' : 'Jobs'}</h1><p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Search roles, refine the results, and open any listing for its full details.</p></div>
      {canManageJobs && <Button onClick={openCreate}>+ New job</Button>}
    </div>

    {isApplicant && resumes.length === 0 && <div className="mb-5 flex items-center justify-between gap-4 rounded-xl border border-indigo-200 bg-indigo-50 px-5 py-4 dark:border-indigo-900 dark:bg-indigo-950/60"><div><p className="text-sm font-semibold text-indigo-950 dark:text-indigo-100">Upload your resume to start applying</p><p className="mt-1 text-xs text-indigo-800 dark:text-indigo-200">You can browse jobs now. Add a resume before submitting an application.</p></div><Button size="sm" onClick={() => navigate('/profile')}>Upload resume</Button></div>}

    <form onSubmit={applySearch} className="mb-4 flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900"><label htmlFor="job-search" className="sr-only">Search jobs</label><span className="pl-2 text-slate-400" aria-hidden="true">⌕</span><input id="job-search" value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="Search by role, skills, company, or keyword" className="min-w-0 flex-1 border-0 bg-transparent px-1 py-2 text-sm focus:outline-none focus:ring-0 dark:text-slate-100" /><Button type="submit">Search</Button>{query && <Button variant="subtle" onClick={() => { setSearchText(''); setQuery(''); setPage(1) }}>Clear</Button>}</form>

    {canFilterByStatus && <div className="mb-4 flex items-center justify-between gap-4"><div className="flex gap-2">{STATUS_OPTIONS.map((option) => <button key={option} onClick={() => { setFilters((current) => ({ ...current, status: option })); setPage(1) }} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${filters.status === option ? 'bg-indigo-700 text-white' : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700 dark:hover:bg-slate-800'}`}>{formatEnumLabel(option)}</button>)}</div><p className="text-xs tabular-nums text-slate-500 dark:text-slate-400">{total.toLocaleString()} result{total === 1 ? '' : 's'}</p></div>}

    <JobFilterBar filters={filters} onChange={changeFilters} />
    <JobList jobs={jobs} loading={loading} error={error} onRetry={refetch} onSelectJob={setSelectedJob} onUploadJD={setUploadJob} isApplicant={isApplicant} myApplicationsByJob={myApplicationsByJob} onApply={handleApply} onWithdraw={handleWithdraw} applyingJobId={applyingJobId} stageCounts={stageCounts} />
    {!loading && !error && <div className="mt-4 flex items-center justify-between"><p className="text-xs text-slate-500 dark:text-slate-400">Showing {total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}</p><Pagination page={page} totalPages={totalPages} onPageChange={setPage} disabled={loading} /></div>}

    <JobDetailsModal open={Boolean(selectedJob)} onClose={() => setSelectedJob(null)} job={selectedJob} onEdit={openEdit} onChanged={handleChanged} onDeleted={refetch} myApplication={selectedJob ? myApplicationsByJob[selectedJob.id] : null} onApplicationChanged={handleApplicationChanged} />
    <JobFormDrawer open={formOpen} onClose={() => setFormOpen(false)} job={editingJob} onSaved={refetch} />
    <JDUploadModal open={Boolean(uploadJob)} onClose={() => setUploadJob(null)} job={uploadJob} onUploaded={handleUploaded} />
  </div>
}
