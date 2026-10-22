// frontend/src/components/jobs/JDUploadModal.jsx
import { useState } from 'react'
import Modal from '../ui/Modal'
import Spinner from '../ui/Spinner'
import Button from '../ui/Button'
import FilePicker from '../ui/FilePicker'
import { uploadJobDescription } from '../../api/jobs'
import { useToast } from '../ui/Toast'
import { getErrorMessage } from '../../utils/format'

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
          ? getErrorMessage(err, 'That file type is not supported.')
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
          <Button variant="secondary" onClick={onClose} disabled={submitting}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={!file || submitting}>
            {submitting ? <Spinner size="sm" label="Uploading" /> : 'Upload'}
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit}>
        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">File</label>
        <FilePicker files={file ? [file] : []} onChange={(fs) => setFile(fs[0] ?? null)} disabled={submitting} />
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">Skills are extracted from the file automatically after upload.</p>
        {job?.jd_raw_text && (
          <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
            This job already has an extracted JD on file — uploading a new one replaces it.
          </p>
        )}
      </form>
    </Modal>
  )
}