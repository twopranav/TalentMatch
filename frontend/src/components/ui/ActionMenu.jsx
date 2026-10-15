import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export default function ActionMenu({ label = 'Actions', items = [], trigger, align = 'end' }) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState(null)
  const triggerRef = useRef(null)
  const menuRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const closeOutside = (event) => {
      if (triggerRef.current?.contains(event.target) || menuRef.current?.contains(event.target)) return
      setOpen(false)
    }
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    const closeOnViewportChange = () => setOpen(false)
    document.addEventListener('mousedown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    window.addEventListener('resize', closeOnViewportChange)
    window.addEventListener('scroll', closeOnViewportChange, true)
    return () => {
      document.removeEventListener('mousedown', closeOutside)
      document.removeEventListener('keydown', closeOnEscape)
      window.removeEventListener('resize', closeOnViewportChange)
      window.removeEventListener('scroll', closeOnViewportChange, true)
    }
  }, [open])

  useLayoutEffect(() => {
    if (!open) { setPosition(null); return }
    const button = triggerRef.current?.getBoundingClientRect()
    const menu = menuRef.current?.getBoundingClientRect()
    if (!button || !menu) return
    const openAbove = button.bottom + menu.height + 8 > window.innerHeight && button.top > menu.height + 8
    const left = align === 'start' ? button.left : button.right - menu.width
    setPosition({ top: openAbove ? button.top - menu.height - 6 : button.bottom + 6, left: Math.max(8, Math.min(left, window.innerWidth - menu.width - 8)) })
  }, [open, align, items.length])

  const selectable = items.filter((item) => !item.disabled)
  const select = (item) => {
    setOpen(false)
    item.onSelect?.()
  }

  return <>
    <button ref={triggerRef} type="button" aria-label={label} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((value) => !value)} className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-[#fbfaf7] px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-indigo-200 hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800">
      {trigger ?? <><span>Actions</span><span aria-hidden="true" className="ml-1 text-slate-400">⌄</span></>}
    </button>
    {open && createPortal(<div ref={menuRef} role="menu" aria-label={label} style={{ position: 'fixed', top: position?.top ?? 0, left: position?.left ?? 0, visibility: position ? 'visible' : 'hidden' }} className="z-[100] min-w-48 overflow-hidden rounded-xl border border-slate-200 bg-[#fbfaf7] p-1 shadow-xl shadow-slate-950/10 ring-1 ring-slate-950/5 dark:border-slate-700 dark:bg-slate-900 dark:ring-white/10">
      {items.map((item, index) => <button key={`${item.label}-${index}`} type="button" role="menuitem" disabled={item.disabled} onClick={() => select(item)} className={`flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-xs font-semibold transition disabled:opacity-50 ${item.danger ? 'text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50' : 'text-slate-700 hover:bg-indigo-50 hover:text-indigo-800 dark:text-slate-200 dark:hover:bg-indigo-950/50 dark:hover:text-indigo-200'}`}>
        <span>{item.label}</span>{item.badge != null && Number(item.badge) > 0 && <span className="rounded-full bg-amber-400/20 px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-amber-800 dark:text-amber-300">{item.badge}</span>}
      </button>)}
      {!selectable.length && <p className="px-3 py-2 text-xs text-slate-400">No actions available</p>}
    </div>, document.body)}
  </>
}
