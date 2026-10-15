import { useEffect, useRef } from 'react'

const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

export default function Modal({ open, onClose, title, children, footer, size = 'lg' }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const previousFocus = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const dialog = dialogRef.current
    const focusFirst = () => {
      const focusable = dialog?.querySelectorAll(FOCUSABLE)
      if (focusable?.length) focusable[0].focus()
      else dialog?.focus()
    }
    const frame = window.requestAnimationFrame(focusFirst)

    const handleKey = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = [...(dialog?.querySelectorAll(FOCUSABLE) ?? [])].filter((element) => element.getClientRects().length)
      if (!focusable.length) {
        event.preventDefault()
        dialog?.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && (document.activeElement === first || !dialog?.contains(document.activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || !dialog?.contains(document.activeElement))) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => {
      window.cancelAnimationFrame(frame)
      document.removeEventListener('keydown', handleKey)
      document.body.style.overflow = previousOverflow
      if (previousFocus?.isConnected && typeof previousFocus.focus === 'function') previousFocus.focus()
    }
  }, [open, onClose])

  if (!open) return null
  const width = size === 'xl' ? 'max-w-4xl' : size === 'md' ? 'max-w-md' : 'max-w-2xl'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <div className="absolute inset-0 bg-slate-950/45 backdrop-blur-sm dark:bg-slate-950/75" aria-hidden="true" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        tabIndex={-1}
        className={`relative z-10 flex max-h-[90vh] w-full ${width} flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-[#fbfaf7] shadow-2xl shadow-slate-950/20 ring-1 ring-slate-950/5 dark:border-slate-700 dark:bg-slate-900 dark:ring-white/10`}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200/80 px-6 py-4 dark:border-slate-700">
          <h2 id="modal-title" className="font-display text-2xl font-semibold text-slate-900 dark:text-slate-100">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close dialog" className="rounded-lg px-2 py-0.5 text-xl leading-none text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 dark:hover:bg-slate-800 dark:hover:text-slate-100">×</button>
        </div>
        <div className="overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="flex shrink-0 flex-wrap justify-end gap-3 border-t border-slate-200/80 px-6 py-4 dark:border-slate-700">{footer}</div>}
      </div>
    </div>
  )
}
