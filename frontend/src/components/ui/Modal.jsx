// frontend/src/components/ui/Modal.jsx
import { useEffect } from 'react'

export default function Modal({ open, onClose, title, children, footer }) {
  useEffect(() => {
    if (!open) return
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/50 dark:bg-slate-950/70"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* max-h + flex-col + overflow-y-auto on the body: previously this had
          no height cap, so a long form (JobFormDrawer) or a long JD text
          block could overflow the viewport with nothing to scroll. Header
          and footer now stay pinned; only the body scrolls. */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        className="relative z-10 flex max-h-[90vh] w-full max-w-lg flex-col rounded-lg bg-white shadow-xl dark:bg-slate-900"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-700">
          <h2 id="modal-title" className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            {title}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 focus:outline-none focus:ring-2 focus:ring-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            ×
          </button>
        </div>

        <div className="overflow-y-auto px-6 py-5">{children}</div>

        {footer && (
          <div className="flex shrink-0 flex-wrap justify-end gap-3 border-t border-slate-200 px-6 py-4 dark:border-slate-700">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}