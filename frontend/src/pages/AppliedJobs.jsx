import { useMemo, useState } from 'react'
import { fetchJob } from '../api/jobs'
import { withdrawApplication } from '../api/applications'
import { useMyApplications } from '../hooks/useApplications'
import JobDetailsModal from '../components/jobs/JobDetailsModal'
import Spinner from '../components/ui/Spinner'
import Button from '../components/ui/Button'
import StatusBadge from '../components/ui/StatusBadge'
import { useToast } from '../components/ui/Toast'
import { formatEnumLabel, getErrorMessage } from '../utils/format'

const FILTERS = ['all', 'applied', 'under_review', 'shortlisted', 'rejected', 'hired']
export default function AppliedJobs() {
  const { applications, loading, error, refetch } = useMyApplications()
  const { showToast } = useToast()
  const [statusFilter, setStatusFilter] = useState('all')
  const [selectedJob, setSelectedJob] = useState(null)
  const [selectedApplication, setSelectedApplication] = useState(null)
  const [openingId, setOpeningId] = useState(null)
  const [withdrawingId, setWithdrawingId] = useState(null)
  const filtered = useMemo(() => applications.filter((app) => statusFilter === 'all' || app.status === statusFilter), [applications, statusFilter])
  const openJob = async (application) => {
    setOpeningId(application.id)
    try { const job = await fetchJob(application.job_id); setSelectedJob(job); setSelectedApplication(application) }
    catch { showToast('Could not load this job.', 'error') }
    finally { setOpeningId(null) }
  }
  const withdraw = async (application) => {
    setWithdrawingId(application.id)
    try { await withdrawApplication(application.id); showToast('Application withdrawn.', 'success'); refetch() }
    catch (err) { showToast(getErrorMessage(err, 'Could not withdraw this application.'), 'error') }
    finally { setWithdrawingId(null) }
  }

  return <div className="mx-auto max-w-360 px-8 py-8">
    <div className="mb-7 flex items-end justify-between gap-6"><div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600 dark:text-indigo-300">Your application tracker</p><h1 className="text-5xl font-semibold text-slate-900 dark:text-slate-100">Applied jobs</h1><p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Keep track of your applications and their current stage.</p></div><span className="rounded-xl bg-indigo-50 px-4 py-2 text-sm font-semibold text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">{applications.length} total</span></div>
    <div className="mb-4 flex items-center gap-2">{FILTERS.map((filter) => <button key={filter} onClick={() => setStatusFilter(filter)} className={`rounded-lg px-3 py-2 text-xs font-semibold ${statusFilter === filter ? 'bg-indigo-700 text-white' : 'bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700 dark:hover:bg-slate-800'}`}>{filter === 'all' ? 'All statuses' : formatEnumLabel(filter)}</button>)}</div>
    {loading && <div className="flex justify-center py-16"><Spinner size="lg" label="Loading applications" /></div>}
    {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
    {!loading && !error && filtered.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 px-6 py-16 text-center dark:border-slate-700"><p className="text-sm text-slate-500 dark:text-slate-400">{statusFilter === 'all' ? 'You have not applied to any jobs yet.' : `No applications with status “${formatEnumLabel(statusFilter)}”.`}</p></div>}
    {!loading && !error && filtered.length > 0 && <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"><table className="w-full text-left"><thead className="bg-slate-50 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400"><tr><th className="px-5 py-3">Role</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Applied</th><th className="px-4 py-3">Stage / interview</th><th className="px-4 py-3">Actions</th></tr></thead><tbody>{filtered.map((application) => <tr key={application.id} className="border-t border-slate-100 hover:bg-slate-50/70 dark:border-slate-800 dark:hover:bg-slate-800/40"><td className="px-5 py-4"><button onClick={() => openJob(application)} disabled={openingId === application.id} className="text-left font-semibold text-slate-900 hover:text-indigo-700 hover:underline dark:text-slate-100 dark:hover:text-indigo-300">{openingId === application.id ? 'Opening…' : application.job_title}</button><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{[application.company, application.location].filter(Boolean).join(' · ') || '—'}</p></td><td className="px-4 py-4"><StatusBadge status={application.status}>{formatEnumLabel(application.status)}</StatusBadge></td><td className="px-4 py-4 text-sm text-slate-500 dark:text-slate-400">{application.applied_at ? new Date(application.applied_at).toLocaleDateString() : '—'}</td><td className="px-4 py-4"><p className="text-sm text-slate-700 dark:text-slate-200">{application.stage ? formatEnumLabel(application.stage) : application.shortlist_stage ? formatEnumLabel(application.shortlist_stage) : 'Application received'}</p>{application.interview_at && <p className="mt-1 text-xs text-slate-500">{new Date(application.interview_at).toLocaleString()}</p>}</td><td className="px-4 py-4">{!['withdrawn', 'rejected', 'hired'].includes(application.status) && <Button variant="secondary" size="sm" disabled={withdrawingId === application.id} onClick={() => withdraw(application)}>{withdrawingId === application.id ? 'Withdrawing…' : 'Withdraw'}</Button>}</td></tr>)}</tbody></table></div>}
    <JobDetailsModal open={Boolean(selectedJob)} onClose={() => { setSelectedJob(null); setSelectedApplication(null) }} job={selectedJob} onEdit={() => {}} onChanged={() => {}} onDeleted={() => {}} myApplication={selectedApplication} onApplicationChanged={refetch} />
  </div>
}
