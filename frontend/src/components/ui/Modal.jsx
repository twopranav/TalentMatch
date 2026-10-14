import { useEffect, useId, useRef } from 'react'

const FOCUSABLE = 'a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex]:not([tabindex="-1"])'

export default function Modal({ open, onClose, title, children, footer, labelledBy, initialFocusRef }) {
  const dialogRef = useRef(null)
  const previousFocus = useRef(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  const id = useId()
  const titleId = labelledBy ?? `modal-title-${id}`

  useEffect(() => {
    if (!open) return undefined
    previousFocus.current = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const focusInitial = () => {
      if (initialFocusRef?.current) initialFocusRef.current.focus()
      else (dialogRef.current?.querySelector(FOCUSABLE) ?? dialogRef.current)?.focus()
    }
    const raf = window.requestAnimationFrame(focusInitial)
    const handleKey = (event) => {
      if (event.key === 'Escape') { event.stopPropagation(); onCloseRef.current?.(); return }
      if (event.key !== 'Tab' || !dialogRef.current) return
      const elements = [...dialogRef.current.querySelectorAll(FOCUSABLE)]
      if (!elements.length) { event.preventDefault(); dialogRef.current.focus(); return }
      const first = elements[0]
      const last = elements[elements.length - 1]
      const focusIsInside = dialogRef.current.contains(document.activeElement)
      if (!focusIsInside) { event.preventDefault(); (event.shiftKey ? last : first).focus() }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', handleKey)
    return () => {
      window.cancelAnimationFrame(raf)
      document.removeEventListener('keydown', handleKey)
      document.body.style.overflow = previousOverflow
      previousFocus.current?.focus?.()
    }
  }, [open, initialFocusRef])

  if (!open) return null
  return <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
    <button type="button" className="animate-fade absolute inset-0 cursor-default bg-slate-950/50 backdrop-blur-sm" onClick={onClose} aria-label="Close dialog backdrop" />
    <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={title ? titleId : undefined} className="animate-pop relative z-10 flex max-h-[90vh] w-full max-w-lg flex-col rounded-2xl bg-white shadow-2xl ring-1 ring-slate-900/10 dark:bg-slate-900 dark:ring-white/10">
      <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-700">
        {title && <h2 id={titleId} className="font-display text-2xl font-semibold text-slate-900 dark:text-slate-100">{title}</h2>}
        <button type="button" onClick={onClose} aria-label="Close" className="ml-auto rounded-lg px-2 py-0.5 text-xl leading-none text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200">×</button>
      </div>
      <div className="overflow-y-auto px-6 py-5">{children}</div>
      {footer && <div className="flex shrink-0 flex-wrap justify-end gap-3 border-t border-slate-200 px-6 py-4 dark:border-slate-700">{footer}</div>}
    </div>
  </div>
}
