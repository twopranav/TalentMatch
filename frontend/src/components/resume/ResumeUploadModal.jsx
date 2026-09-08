// frontend/src/components/resumes/ResumeUploadModal.jsx
import { useState } from 'react'
import Modal from '../ui/Modal'
import Spinner from '../ui/Spinner'
import { uploadResume } from '../../api/resumes'
import { useToast } from '../ui/Toast'

export default function ResumeUploadModal({ open, onClose, currentResume, onUploaded }) {
  const [file, setFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const { showToast } = useToast()

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!file) return
    setSubmitting(true)
    try {
      const uploaded = await uploadResume(file)
      showToast('Resume uploaded.', 'success')
      onUploaded(uploaded)
      onClose()
      setFile(null)
    } catch (err) {
      // Backend rejects unsupported types with 415, oversized files with 413 —
      // surface both distinctly instead of the generic failure message.
      const message =
        err.response?.status === 415 || err.response?.status === 413
          ? err.response?.data?.detail || 'That file could not be uploaded.'
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
      title="Upload your resume"
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
        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
          File (PDF or DOCX, max 10MB)
        </label>
        <input
          type="file"
          accept=".pdf,.docx"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="w-full text-sm text-slate-600 dark:text-slate-300"
        />
        {currentResume && (
          <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
            You already have a resume on file ({currentResume.original_filename}) — uploading a new one replaces it.
          </p>
        )}
      </form>
    </Modal>
  )
}