import { useEffect, useState } from 'react'
import { fetchResumes, uploadResumesBulk, archiveResume, deleteResume, openResumeFile } from '../api/resumes'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import Spinner from '../components/ui/Spinner'
import { useToast } from '../components/ui/Toast'
import { getErrorMessage } from '../utils/format'
import ResumeExtractionModal, { ExtractionStatusBadge } from '../components/resume/ResumeExtractionModal'

const STATUS_STYLES = {
  uploaded: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
}

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
    <div className="mb-6 rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-3 text-sm font-semibold text-slate-900 dark:text-slate-100">Bulk upload</h2>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        Source resumes for candidates who don't have an account yet. One bad file in the batch won't stop the rest.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="file"
          accept=".pdf,.docx"
          multiple
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          className="text-sm text-slate-600 dark:text-slate-300"
        />
        <button
          onClick={handleSubmit}
          disabled={files.length === 0 || submitting}
          className="flex items-center gap-2 rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600"
        >
          {submitting ? <Spinner size="sm" label="Uploading" /> : `Upload ${files.length || ''} file${files.length === 1 ? '' : 's'}`}
        </button>
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

  const load = () => {
    setLoading(true)
    setError(null)
    fetchResumes(showArchived)
      .then(setResumes)
      .catch((err) => setError(getErrorMessage(err, 'Could not load resumes.')))
      .finally(() => setLoading(false))
  }

  useEffect(load, [showArchived])

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
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Resume Library</h1>
        <button
          onClick={() => setShowArchived((v) => !v)}
          className={`rounded px-3 py-1.5 text-sm font-medium ${
            showArchived
              ? 'bg-slate-800 text-white dark:bg-slate-700'
              : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
          }`}
        >
          {showArchived ? 'Showing archived' : 'Show archived'}
        </button>
      </div>

      <BulkUpload onDone={load} />

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        {loading ? (
          <div className="flex justify-center py-16"><Spinner size="lg" label="Loading resumes" /></div>
        ) : error ? (
          <div className="px-6 py-8 text-center">
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            <button onClick={load} className="mt-3 text-sm font-medium text-red-800 underline hover:no-underline dark:text-red-300">
              Try again
            </button>
          </div>
        ) : resumes.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <p className="text-sm text-slate-500 dark:text-slate-400">No resumes yet.</p>
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-400 dark:bg-slate-800 dark:text-slate-500">
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
              {resumes.map((r) => (
                <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-4 py-2 text-slate-700 dark:text-slate-300">{r.original_filename}</td>
                  <td className="px-4 py-2 text-slate-600 dark:text-slate-400">
                    {r.candidate_name || r.candidate_email || r.owner_email || 'Unclaimed'}
                  </td>
                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{r.uploaded_by_email || '—'}</td>
                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{formatSize(r.size_bytes)}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[r.status]}`}>
                      {r.status}
                    </span>
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
                      <ExtractionStatusBadge status={r.extraction_status} />
                    </button>
                  </td>
                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{new Date(r.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-3 text-xs">
                      <button onClick={() => handleView(r)} disabled={openingId === r.id} className="font-medium text-slate-700 underline hover:no-underline disabled:opacity-50 dark:text-slate-300">
                        {openingId === r.id ? 'Opening…' : 'View'}
                      </button>
                      <button onClick={() => handleToggleArchive(r)} disabled={busyId === r.id} className="font-medium text-slate-700 underline hover:no-underline disabled:opacity-50 dark:text-slate-300">
                        {r.is_archived ? 'Restore' : 'Archive'}
                      </button>
                      <button onClick={() => setDeleteTarget(r)} disabled={busyId === r.id} className="font-medium text-red-600 underline hover:no-underline disabled:opacity-50 dark:text-red-400">
                        Delete
                      </button>
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
        resume={extractionTarget}
      />
    </div>
  )
}