// frontend/src/components/resume/ResumePreview.jsx
import { useEffect, useRef, useState } from 'react'
import Spinner from '../ui/Spinner'
import { fetchResumeBlobUrl, openResumeFile } from '../../api/resumes'

// Browsers only know how to render PDFs inline via <iframe>. DOCX (and
// anything else the backend might allow later) has no native in-browser
// renderer, so those fall back to "open in a new tab" instead of a blank
// or broken iframe.
const INLINE_PREVIEWABLE_CONTENT_TYPES = new Set(['application/pdf'])

export default function ResumePreview({ resume }) {
  const [previewUrl, setPreviewUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [opening, setOpening] = useState(false)
  const objectUrlRef = useRef(null)

  const canPreviewInline = !!resume && INLINE_PREVIEWABLE_CONTENT_TYPES.has(resume.content_type)

  useEffect(() => {
    // Whatever blob URL we were holding for the previous resume is no
    // longer valid once the resume changes (e.g. after a replace) — revoke
    // it so it doesn't leak for the life of the tab.
    if (objectUrlRef.current) {
      window.URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    setPreviewUrl(null)
    setError(null)

    if (!canPreviewInline) return

    let cancelled = false
    setLoading(true)
    fetchResumeBlobUrl(resume.id)
      .then((url) => {
        if (cancelled) {
          window.URL.revokeObjectURL(url)
          return
        }
        objectUrlRef.current = url
        setPreviewUrl(url)
      })
      .catch(() => {
        if (!cancelled) setError('Could not load a preview of this resume.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [resume?.id, canPreviewInline])

  // Final cleanup on unmount.
  useEffect(() => () => {
    if (objectUrlRef.current) window.URL.revokeObjectURL(objectUrlRef.current)
  }, [])

  const handleOpen = async () => {
    setOpening(true)
    try {
      await openResumeFile(resume.id)
    } finally {
      setOpening(false)
    }
  }

  if (!resume) return null

  return (
    <div className="mt-3 overflow-hidden rounded border border-slate-200 dark:border-slate-700">
      {canPreviewInline ? (
        loading ? (
          <div className="flex justify-center py-10"><Spinner size="sm" label="Loading preview" /></div>
        ) : error ? (
          <p className="p-4 text-xs text-red-600 dark:text-red-400">{error}</p>
        ) : previewUrl ? (
          <iframe
            title={`Preview of ${resume.original_filename}`}
            src={previewUrl}
            className="h-96 w-full bg-white"
          />
        ) : null
      ) : (
        <div className="flex flex-col items-center gap-2 py-8 text-center">
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Preview isn't available for this file type ({resume.original_filename}).
          </p>
          <button
            onClick={handleOpen}
            disabled={opening}
            className="text-xs font-medium text-slate-700 underline hover:no-underline disabled:opacity-50 dark:text-slate-300"
          >
            {opening ? 'Opening…' : 'Open in a new tab'}
          </button>
        </div>
      )}
    </div>
  )
}