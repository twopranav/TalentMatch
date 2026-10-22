import { EmptyArt } from '../components/ui/Ornaments'
import { useEffect, useState } from 'react'
import { fetchResumes, uploadResumesBulk, archiveResume, deleteResume, openResumeFile, rerunResumeExtraction } from '../api/resumes'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import Spinner from '../components/ui/Spinner'
import FilePicker from '../components/ui/FilePicker'
import { useToast } from '../components/ui/Toast'
import { formatEnumLabel, getErrorMessage } from '../utils/format'
import ResumeExtractionModal, { ExtractionStatusBadge } from '../components/resume/ResumeExtractionModal'
import StatusBadge from '../components/ui/StatusBadge'
import PageHeader from '../components/ui/PageHeader'
import Button from '../components/ui/Button'

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function BulkUpload({ onDone }) {
  const [files, setFiles] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [results, setResults] = useState(null)
  const { showToast } = useToast()

  const handleSubmit = async () => {
    if (files.length === 0) return
    setSubmitting(true)
    setResults(null)
    try {
      const outcome = await uploadResumesBulk(files)
      setResults(outcome)
      const succeeded = outcome.filter((r) => r.success).length
      const failed = outcome.length - succeeded
      showToast(
        failed === 0
          ? `${succeeded} resume${succeeded === 1 ? '' : 's'} uploaded.`
          : `${succeeded} uploaded, ${failed} failed.`,
        failed === 0 ? 'success' : 'error',
      )
      setFiles([])
      onDone()
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not upload those files.'), 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mb-6 rounded-2xl border border-slate-200/80 bg-[#fbfaf7]/95 p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900/90">
      <h2 className="font-display mb-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">Bulk upload</h2>
      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        Source resumes for candidates who don't have an account yet (PDF or DOCX). One bad file in the batch won't stop the rest.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <FilePicker files={files} onChange={setFiles} accept=".pdf,.docx" multiple disabled={submitting} label="Choose resume files" />
        <Button onClick={handleSubmit} disabled={files.length === 0 || submitting}>
          {submitting ? <Spinner size="sm" label="Uploading" /> : files.length ? `Upload ${files.length} file${files.length === 1 ? '' : 's'}` : 'Upload files'}
        </Button>
      </div>

      {results && (
        <ul className="mt-4 space-y-1 text-xs">
          {results.map((r, i) => (
            <li key={i} className={r.success ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}>
              {r.success ? '✓' : '✗'} {r.original_filename}{!r.success && r.error ? ` — ${r.error}` : ''}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function ResumeLibrary() {
  const { showToast } = useToast()
  const [resumes, setResumes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showArchived, setShowArchived] = useState(false)
  const [openingId, setOpeningId] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [extractionTarget, setExtractionTarget] = useState(null)
  const [rerunning, setRerunning] = useState(false)
  const [search, setSearch] = useState('')

  const load = () => {
    setLoading(true)
    setError(null)
    fetchResumes(showArchived)
      .then(setResumes)
      .catch((err) => setError(getErrorMessage(err, 'Could not load resumes.')))
      .finally(() => setLoading(false))
  }

  useEffect(load, [showArchived])

  // Auto-refresh while any resume is still being extracted, so the badge
  // flips to Done/Failed without a manual reload. Polls quietly (no
  // spinner) every 4s and gives up after ~3 minutes so a resume stuck at
  // Pending can't keep the page polling forever.
  const hasInFlight = resumes.some((r) => {
    const s = String(r.skills_extraction_status ?? r.extraction_status ?? '').toLowerCase()
    return s === 'pending' || s === 'processing'
  })

  useEffect(() => {
    if (!hasInFlight) return undefined
    let polls = 0
    const id = setInterval(() => {
      polls += 1
      if (polls > 45) {
        clearInterval(id)
        return
      }
      fetchResumes(showArchived).then(setResumes).catch(() => {})
    }, 4000)
    return () => clearInterval(id)
  }, [hasInFlight, showArchived])

  const term = search.trim().toLowerCase()
  const visibleResumes = term
    ? resumes.filter((r) => [r.original_filename, r.candidate_name, r.candidate_email, r.owner_email, r.uploaded_by_email].some((v) => String(v ?? '').toLowerCase().includes(term)))
    : resumes

  // The open modal should follow the refreshed data, not a stale snapshot.
  const liveExtractionTarget = extractionTarget
    ? resumes.find((r) => r.id === extractionTarget.id) ?? extractionTarget
    : null

  const handleView = async (resume) => {
    setOpeningId(resume.id)
    try {
      await openResumeFile(resume.id)
    } catch {
      showToast('Could not open that resume.', 'error')
    } finally {
      setOpeningId(null)
    }
  }

  // Flips the row to Pending on the server; the in-flight poll above then follows it to Done/Failed.
  const handleRerun = async () => {
    if (!extractionTarget) return
    setRerunning(true)
    try {
      const updated = await rerunResumeExtraction(extractionTarget.id)
      setResumes((current) => current.map((r) => (r.id === updated.id ? { ...r, ...updated } : r)))
      showToast('Extraction restarted.', 'success')
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not restart extraction.'), 'error')
    } finally {
      setRerunning(false)
    }
  }

  const handleToggleArchive = async (resume) => {
    setBusyId(resume.id)
    try {
      await archiveResume(resume.id, !resume.is_archived)
      showToast(resume.is_archived ? 'Resume restored.' : 'Resume archived.', 'success')
      load()
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not update this resume.'), 'error')
    } finally {
      setBusyId(null)
    }
  }

  const handleDelete = async () => {
    const resume = deleteTarget
    if (!resume) return
    setBusyId(resume.id)
    try {
      await deleteResume(resume.id)
      showToast('Resume deleted.', 'success')
      load()
    } catch (err) {
      showToast(getErrorMessage(err, 'Could not delete this resume.'), 'error')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="mx-auto max-w-[1440px] px-8 py-8">
      <PageHeader
        eyebrow="Talent pool"
        title="Resume library"
        description="Resumes you can add to a job as applicants. Open one to review its extracted skills."
        meta={!loading && !error && <span className="text-xs tabular-nums text-slate-500 dark:text-slate-400">{resumes.length} {showArchived ? 'resumes including archived' : resumes.length === 1 ? 'resume' : 'resumes'}</span>}
      />

      <BulkUpload onDone={load} />

      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-[#fbfaf7]/90 p-3 dark:border-slate-800 dark:bg-slate-900/90">
        <label htmlFor="resume-search" className="sr-only">Search resumes</label>
        <input id="resume-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by file, candidate, or uploader" className="min-w-72 flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100" />
        <label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-slate-600 dark:text-slate-300">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
          Include archived
        </label>
        {term && <span className="text-xs tabular-nums text-slate-500 dark:text-slate-400">{visibleResumes.length} match{visibleResumes.length === 1 ? '' : 'es'}</span>}
      </div>

      <div className="overflow-x-auto rounded-2xl border border-slate-200/80 bg-[#fbfaf7]/95 shadow-sm dark:border-slate-800 dark:bg-slate-900/90">
        {loading ? (
          <div className="flex justify-center py-16"><Spinner size="lg" label="Loading resumes" /></div>
        ) : error ? (
          <div className="px-6 py-8 text-center">
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            <button onClick={load} className="mt-3 text-sm font-medium text-red-800 underline hover:no-underline dark:text-red-300">
              Try again
            </button>
          </div>
        ) : visibleResumes.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <EmptyArt variant="resumes" />
            <p className="text-sm text-slate-500 dark:text-slate-400">{term ? 'No resumes match this search.' : 'No resumes yet. Use bulk upload above to add some.'}</p>
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              <tr>
                <th className="px-4 py-2 font-medium">File</th>
                <th className="px-4 py-2 font-medium">Candidate</th>
                <th className="px-4 py-2 font-medium">Uploaded by</th>
                <th className="px-4 py-2 font-medium">Size</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Extraction</th>
                <th className="px-4 py-2 font-medium">Added</th>
                <th className="px-4 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleResumes.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50/70 dark:border-slate-800 dark:hover:bg-slate-800/40">
                  <td className="px-4 py-2 text-slate-700 dark:text-slate-300">{r.original_filename}</td>
                  <td className="px-4 py-2 text-slate-600 dark:text-slate-400">
                    {r.candidate_name || r.candidate_email || r.owner_email || 'Unclaimed'}
                  </td>
                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{r.uploaded_by_email || '—'}</td>
                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{formatSize(r.size_bytes)}</td>
                  <td className="px-4 py-2">
                    <StatusBadge status={r.status}>{formatEnumLabel(r.status)}</StatusBadge>
                    {r.is_archived && (
                      <span className="ml-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                        archived
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => setExtractionTarget(r)}
                      className="rounded-full hover:opacity-80"
                      title="View extraction details"
                    >
                      <ExtractionStatusBadge status={r.skills_extraction_status ?? r.extraction_status} />
                    </button>
                  </td>
                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{new Date(r.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-1.5">
                      <Button size="sm" variant="secondary" onClick={() => handleView(r)} disabled={openingId === r.id}>{openingId === r.id ? 'Opening…' : 'View'}</Button>
                      <Button size="sm" variant="subtle" onClick={() => handleToggleArchive(r)} disabled={busyId === r.id}>{r.is_archived ? 'Restore' : 'Archive'}</Button>
                      <Button size="sm" variant="subtle" onClick={() => setDeleteTarget(r)} disabled={busyId === r.id} className="!text-red-600 hover:!bg-red-50 dark:!text-red-400 dark:hover:!bg-red-950/50">Delete</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Delete this resume?"
        message={`"${deleteTarget?.original_filename}" will be permanently removed. This can't be undone.`}
        confirmLabel="Delete"
        destructive
      />

      <ResumeExtractionModal
        open={Boolean(extractionTarget)}
        onClose={() => setExtractionTarget(null)}
        resume={liveExtractionTarget}
        onRerun={handleRerun}
        rerunning={rerunning}
      />
    </div>
  )
}