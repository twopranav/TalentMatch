// frontend/src/components/jobs/JDUploadModal.jsx
import { useState } from 'react'
import Modal from '../ui/Modal'
import Spinner from '../ui/Spinner'
import { uploadJobDescription } from '../../api/jobs'
import { useToast } from '../ui/Toast'

export default function JDUploadModal({ open, onClose, job, onUploaded }) {
  const [file, setFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const { showToast } = useToast()

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!file) return
    setSubmitting(true)
    try {
      const updated = await uploadJobDescription(job.id, file)
      showToast('Job description uploaded.', 'success')
      onUploaded(updated)
      onClose()
      setFile(null)
    } catch (err) {
      // Backend rejects unsupported extensions with 400 — surface that
      // distinctly instead of the generic failure message.
      const message =
        err.response?.status === 400
          ? err.response?.data?.detail || 'That file type is not supported.'
          : 'Could not upload the file. Please try again.'
      showToast(message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`Upload job description — ${job?.title ?? ''}`}
      footer={
        <>
          <button onClick={onClose} className="rounded px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!file || submitting}
            className="flex items-center gap-2 rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600"
          >
            {submitting ? <Spinner size="sm" label="Uploading" /> : 'Upload'}
          </button>
        </>
      }
    >
      <form onSubmit={handleSubmit}>
        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">File</label>
        <input
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="w-full text-sm text-slate-600 dark:text-slate-300"
        />
        {job?.jd_raw_text && (
          <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
            This job already has an extracted JD on file — uploading a new one replaces it.
          </p>
        )}
      </form>
    </Modal>
  )
}