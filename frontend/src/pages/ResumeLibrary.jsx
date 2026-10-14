import { useCallback, useEffect, useState } from 'react'
import { EmptyArt } from '../components/ui/Ornaments'
import { fetchResumesPage, uploadResumesBulk, archiveResume, deleteResume, openResumeFile, retryResumeExtraction } from '../api/resumes'
import { fetchJobs } from '../api/jobs'
import { bulkApplyResumes } from '../api/applications'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import Spinner from '../components/ui/Spinner'
import FilePicker from '../components/ui/FilePicker'
import Pagination from '../components/ui/Pagination'
import Modal from '../components/ui/Modal'
import Button from '../components/ui/Button'
import Field from '../components/ui/Field'
import StatusBadge from '../components/ui/StatusBadge'
import ActionMenu from '../components/ui/ActionMenu'
import { useToast } from '../components/ui/Toast'
import { getErrorMessage } from '../utils/format'
import ResumeExtractionModal from '../components/resume/ResumeExtractionModal'

const PAGE_SIZE = 25
const BATCH_SIZE = 20
function formatSize(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function BulkUpload({ onDone }) {
  const [files, setFiles] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [results, setResults] = useState(null)
  const [progress, setProgress] = useState(0)
  const [batchLabel, setBatchLabel] = useState('')
  const { showToast } = useToast()

  const handleSubmit = async () => {
    if (!files.length) return
    setSubmitting(true); setResults([]); setProgress(0)
    const accumulated = []
    try {
      for (let start = 0; start < files.length; start += BATCH_SIZE) {
        const batch = files.slice(start, start + BATCH_SIZE)
        setBatchLabel(`Uploading batch ${Math.floor(start / BATCH_SIZE) + 1} of ${Math.ceil(files.length / BATCH_SIZE)}`)
        try {
          const outcome = await uploadResumesBulk(batch, (event) => {
            if (event.total) setProgress(Math.min(100, Math.round(((start + (event.loaded / event.total) * batch.length) / files.length) * 100)))
          })
          const rows = Array.isArray(outcome) ? outcome : (outcome.items ?? outcome.results ?? [])
          accumulated.push(...rows.map((row) => ({ ...row, success: row.success ?? row.ok ?? true })))
          if (!rows.length) batch.forEach((file) => accumulated.push({ original_filename: file.name, success: true }))
        } catch (error) {
          batch.forEach((file) => accumulated.push({ original_filename: file.name, success: false, error: getErrorMessage(error, 'Upload failed.') }))
          if (error.response?.status === 429) {
            const retryAfter = Number(error.response.headers?.['retry-after'] ?? 60)
            showToast(`Upload rate limit reached. Wait ${retryAfter} seconds before trying again.`, 'error', 7000)
            break
          }
        }
        setResults([...accumulated])
        setProgress(Math.min(100, Math.round((Math.min(start + batch.length, files.length) / files.length) * 100)))
      }
      const succeeded = accumulated.filter((row) => row.success).length
      const failed = accumulated.length - succeeded
      showToast(failed === 0 ? `${succeeded} resume${succeeded === 1 ? '' : 's'} uploaded.` : `${succeeded} uploaded, ${failed} failed.`, failed === 0 ? 'success' : 'error')
      setResults(accumulated); setFiles([]); onDone()
    } finally { setSubmitting(false); setBatchLabel('') }
  }

  return <section className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
    <div className="mb-3"><h2 className="font-display text-2xl font-semibold text-slate-900 dark:text-slate-100">Bulk upload</h2><p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Add candidate resumes in batches of up to {BATCH_SIZE}. PDF and DOCX files are accepted.</p></div>
    <div className="flex items-center gap-3"><div className="flex-1"><FilePicker files={files} onChange={setFiles} accept=".pdf,.docx" multiple disabled={submitting} label="Choose resume files" /></div><Button onClick={handleSubmit} disabled={!files.length || submitting}>{submitting ? <><Spinner size="sm" label="Uploading" /> Uploading…</> : `Upload ${files.length || ''} file${files.length === 1 ? '' : 's'}`}</Button></div>
    {submitting && <div className="mt-4" aria-live="polite"><div className="mb-1 flex justify-between text-xs text-slate-500 dark:text-slate-400"><span>{batchLabel}</span><span>{progress}%</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"><div className="h-full rounded-full bg-indigo-600 transition-all" style={{ width: `${progress}%` }} /></div></div>}
    {results && <ul className="mt-4 max-h-36 space-y-1 overflow-auto text-xs">{results.map((row, index) => <li key={`${row.original_filename}-${index}`} className={row.success ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}>{row.success ? '✓' : '✗'} {row.original_filename}{!row.success && row.error ? ` — ${row.error}` : ''}</li>)}</ul>}
  </section>
}

export default function ResumeLibrary() {
  const { showToast } = useToast()
  const [resumes, setResumes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showArchived, setShowArchived] = useState(false)
  const [searchDraft, setSearchDraft] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [openingId, setOpeningId] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [retryingId, setRetryingId] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [extractionTarget, setExtractionTarget] = useState(null)
  const [selectedIds, setSelectedIds] = useState([])
  const [sendModalOpen, setSendModalOpen] = useState(false)
  const [jobs, setJobs] = useState([])
  const [selectedJobId, setSelectedJobId] = useState('')
  const [sending, setSending] = useState(false)

  const load = useCallback(() => {
    setLoading(true); setError(null)
    fetchResumesPage({ include_archived: showArchived, q: query || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE })
      .then(({ items, total: count }) => { setResumes(items); setTotal(count); setSelectedIds([]) })
      .catch((err) => setError(getErrorMessage(err, 'Could not load resumes.')))
      .finally(() => setLoading(false))
  }, [showArchived, query, page])
  useEffect(() => { load() }, [load])
  const hasInFlight = resumes.some((resume) => ['pending', 'processing'].includes(String(resume.skills_extraction_status ?? resume.extraction_status ?? '').toLowerCase()))
  useEffect(() => {
    if (!hasInFlight) return undefined
    let polls = 0
    const id = window.setInterval(() => {
      polls += 1
      if (polls > 45) { window.clearInterval(id); return }
      fetchResumesPage({ include_archived: showArchived, q: query || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }).then(({ items }) => setResumes(items)).catch(() => {})
    }, 4000)
    return () => window.clearInterval(id)
  }, [hasInFlight, showArchived, query, page])
  const liveExtractionTarget = extractionTarget ? resumes.find((resume) => resume.id === extractionTarget.id) ?? extractionTarget : null
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const allPageSelected = resumes.length > 0 && resumes.every((resume) => selectedIds.includes(resume.id))

  const handleView = async (resume) => {
    setOpeningId(resume.id)
    try { await openResumeFile(resume.id) }
    catch { showToast('Could not open that resume.', 'error') }
    finally { setOpeningId(null) }
  }
  const handleToggleArchive = async (resume) => {
    setBusyId(resume.id)
    try { await archiveResume(resume.id, !resume.is_archived); showToast(resume.is_archived ? 'Resume restored.' : 'Resume archived.', 'success'); load() }
    catch (err) { showToast(getErrorMessage(err, 'Could not update this resume.'), 'error') }
    finally { setBusyId(null) }
  }
  const handleDelete = async () => {
    const resume = deleteTarget
    if (!resume) return
    setBusyId(resume.id)
    try { await deleteResume(resume.id); showToast('Resume deleted.', 'success'); setDeleteTarget(null); load() }
    catch (err) { showToast(getErrorMessage(err, 'Could not delete this resume.'), 'error') }
    finally { setBusyId(null) }
  }
  const retryExtraction = async (resume) => {
    setRetryingId(resume.id)
    try { await retryResumeExtraction(resume.id); showToast('Extraction retry queued.', 'success'); load() }
    catch (err) {
      if (err.response?.status === 429) { const wait = Number(err.response.headers?.['retry-after'] ?? 60); showToast(`Too many retries. Please wait ${wait} seconds.`, 'error', 7000) }
      else showToast(getErrorMessage(err, 'Could not retry extraction.'), 'error')
    } finally { setRetryingId(null) }
  }
  const openSendModal = async () => {
    try {
      const result = await fetchJobs({ status: 'published', limit: 200 })
      setJobs(Array.isArray(result) ? result : (result.items ?? []))
      setSelectedJobId(''); setSendModalOpen(true)
    } catch { showToast('Could not load published jobs.', 'error') }
  }
  const sendSelected = async () => {
    if (!selectedJobId || !selectedIds.length) return
    setSending(true)
    try {
      const result = await bulkApplyResumes(selectedJobId, selectedIds)
      const accepted = result?.created ?? result?.success_count ?? result?.applied ?? selectedIds.length
      showToast(`${accepted} selected resume${accepted === 1 ? '' : 's'} sent to the job.`, 'success')
      setSelectedIds([]); setSendModalOpen(false)
    } catch (err) {
      if (err.response?.status === 429) { const wait = Number(err.response.headers?.['retry-after'] ?? 60); showToast(`Rate limit reached. Please wait ${wait} seconds.`, 'error', 7000) }
      else showToast(getErrorMessage(err, 'Could not send selected resumes to the job.'), 'error')
    } finally { setSending(false) }
  }
  const updateSelected = (resumeId, checked) => setSelectedIds((current) => checked ? [...new Set([...current, resumeId])] : current.filter((id) => id !== resumeId))
  const submitSearch = (event) => { event.preventDefault(); setQuery(searchDraft.trim()); setPage(1) }
  const extractionState = (resume) => String(resume.skills_extraction_status ?? resume.extraction_status ?? resume.status ?? 'unknown').toLowerCase()

  return <div className="mx-auto max-w-[1440px] px-8 py-8">
    <div className="mb-6 flex items-end justify-between gap-6"><div><p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600 dark:text-indigo-300">Talent pool</p><h1 className="text-5xl font-semibold text-slate-900 dark:text-slate-100">Resume library</h1><p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Search candidate files, review extraction state, or attach selected resumes to a published role.</p></div><Button variant="secondary" onClick={() => { setShowArchived((value) => !value); setPage(1) }}>{showArchived ? 'Hide archived' : 'Show archived'}</Button></div>
    <BulkUpload onDone={load} />
    <form onSubmit={submitSearch} className="mb-4 flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900"><label htmlFor="resume-search" className="sr-only">Search resumes</label><input id="resume-search" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="Search by filename, candidate, or email" className="min-w-0 flex-1 border-0 bg-transparent px-2 py-1.5 text-sm focus:outline-none focus:ring-0 dark:text-slate-100" /><Button size="sm" type="submit">Search</Button>{query && <Button size="sm" variant="subtle" onClick={() => { setSearchDraft(''); setQuery(''); setPage(1) }}>Clear</Button>}<span className="ml-2 text-xs text-slate-500">{total} resumes</span>{selectedIds.length > 0 && <Button size="sm" onClick={openSendModal}>Send selected to a job ({selectedIds.length})</Button>}</form>

    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      {loading ? <div className="flex justify-center py-16"><Spinner size="lg" label="Loading resumes" /></div> : error ? <div className="px-6 py-8 text-center"><p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p><Button variant="secondary" className="mt-3" onClick={load}>Try again</Button></div> : resumes.length === 0 ? <div className="px-6 py-16 text-center"><EmptyArt variant="resumes" /><p className="text-sm text-slate-500 dark:text-slate-400">No resumes match this view.</p></div> : <table className="w-full text-left text-sm"><thead className="bg-slate-50 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400"><tr><th className="w-10 px-4 py-3"><input type="checkbox" aria-label="Select all resumes on this page" checked={allPageSelected} onChange={(event) => setSelectedIds(event.target.checked ? [...new Set([...selectedIds, ...resumes.map((resume) => resume.id)])] : selectedIds.filter((id) => !resumes.some((resume) => resume.id === id)))} /></th><th className="px-4 py-3">File</th><th className="px-4 py-3">Candidate</th><th className="px-4 py-3">Uploaded by</th><th className="px-4 py-3">Size</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Added</th><th className="px-4 py-3">Actions</th></tr></thead><tbody>{resumes.map((resume) => {
        const state = extractionState(resume)
        const failed = ['failed', 'error'].includes(state)
        return <tr key={resume.id} className="border-t border-slate-100 hover:bg-slate-50/70 dark:border-slate-800 dark:hover:bg-slate-800/40"><td className="px-4 py-3"><input type="checkbox" aria-label={`Select ${resume.original_filename}`} checked={selectedIds.includes(resume.id)} onChange={(event) => updateSelected(resume.id, event.target.checked)} /></td><td className="max-w-sm px-4 py-3"><p className="truncate font-medium text-slate-800 dark:text-slate-100">{resume.original_filename}</p>{resume.is_archived && <span className="text-xs text-slate-400">Archived</span>}</td><td className="px-4 py-3 text-slate-600 dark:text-slate-400">{resume.candidate_name || resume.candidate_email || resume.owner_email || 'Unclaimed'}</td><td className="px-4 py-3 text-slate-500 dark:text-slate-400">{resume.uploaded_by_email || '—'}</td><td className="px-4 py-3 text-slate-500 dark:text-slate-400">{formatSize(resume.size_bytes)}</td><td className="px-4 py-3"><div className="flex items-center gap-2"><StatusBadge status={state}>{state.replaceAll('_', ' ')}</StatusBadge>{failed && <button type="button" disabled={retryingId === resume.id} onClick={() => retryExtraction(resume)} className="text-xs font-semibold text-indigo-700 underline disabled:opacity-50 dark:text-indigo-300">{retryingId === resume.id ? 'Retrying…' : 'Retry'}</button>}<button type="button" onClick={() => setExtractionTarget(resume)} className="text-xs text-slate-500 underline hover:no-underline dark:text-slate-400">Details</button></div></td><td className="px-4 py-3 text-slate-500 dark:text-slate-400">{resume.created_at ? new Date(resume.created_at).toLocaleDateString() : '—'}</td><td className="px-4 py-3"><ActionMenu label={`Actions for ${resume.original_filename}`} items={[{ label: openingId === resume.id ? 'Opening…' : 'View file', disabled: openingId === resume.id, onSelect: () => handleView(resume) }, { label: resume.is_archived ? 'Restore' : 'Archive', disabled: busyId === resume.id, onSelect: () => handleToggleArchive(resume) }, { label: 'Delete resume', danger: true, disabled: busyId === resume.id, onSelect: () => setDeleteTarget(resume) }]} /></td></tr>
      })}</tbody></table>}
    </div>
    {!loading && !error && <div className="mt-4 flex items-center justify-between"><p className="text-xs text-slate-500">Showing {total ? (page - 1) * PAGE_SIZE + 1 : 0}–{Math.min(page * PAGE_SIZE, total)} of {total} resumes</p><Pagination page={page} totalPages={totalPages} onPageChange={setPage} disabled={loading} /></div>}

    <ConfirmDialog open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} onConfirm={handleDelete} title="Delete this resume?" message={`“${deleteTarget?.original_filename}” will be permanently removed. This can't be undone.`} confirmLabel="Delete" destructive requireText requiredText="DELETE" />
    <ResumeExtractionModal open={Boolean(extractionTarget)} onClose={() => setExtractionTarget(null)} resume={liveExtractionTarget} />
    <Modal open={sendModalOpen} onClose={() => !sending && setSendModalOpen(false)} title="Send selected resumes to a job" footer={<><Button variant="secondary" disabled={sending} onClick={() => setSendModalOpen(false)}>Cancel</Button><Button disabled={sending || !selectedJobId || !selectedIds.length} onClick={sendSelected}>{sending ? 'Sending…' : `Send ${selectedIds.length} resume${selectedIds.length === 1 ? '' : 's'}`}</Button></>}>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">Selected resumes will be added as applicants to one published job. Existing applications may be skipped by the server.</p>
      <Field as="select" label="Published job" value={selectedJobId} onChange={(event) => setSelectedJobId(event.target.value)} required><option value="">Select a job…</option>{jobs.map((job) => <option key={job.id} value={job.id}>{job.title}</option>)}</Field>
      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">{selectedIds.length} resume{selectedIds.length === 1 ? '' : 's'} selected.</p>
    </Modal>
  </div>
}
