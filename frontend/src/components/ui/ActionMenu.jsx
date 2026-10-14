import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const MENU_WIDTH = 208
const EDGE_GAP = 12

export default function ActionMenu({ label = 'More actions', items = [], align = 'end', trigger = null }) {
  const triggerRef = useRef(null)
  const menuRef = useRef(null)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({ top: 0, left: 0 })
  const enabledItems = items.filter((item) => item && !item.hidden)

  const placeMenu = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const height = menuRef.current?.getBoundingClientRect().height ?? 240
    const topBelow = rect.bottom + 6
    const top = topBelow + height > window.innerHeight - EDGE_GAP
      ? Math.max(EDGE_GAP, rect.top - height - 6)
      : Math.min(topBelow, window.innerHeight - height - EDGE_GAP)
    const desiredLeft = align === 'end' ? rect.right - MENU_WIDTH : rect.left
    const left = Math.max(EDGE_GAP, Math.min(desiredLeft, window.innerWidth - MENU_WIDTH - EDGE_GAP))
    setPosition({ top, left })
  }, [align])

  useEffect(() => {
    if (!open) return undefined
    placeMenu()
    const raf = window.requestAnimationFrame(() => {
      placeMenu()
      menuRef.current?.querySelector('button:not(:disabled)')?.focus()
    })
    const dismiss = (event) => {
      if (!triggerRef.current?.contains(event.target) && !menuRef.current?.contains(event.target)) setOpen(false)
    }
    const keydown = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        setOpen(false)
        triggerRef.current?.focus()
        return
      }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) || !menuRef.current) return
      const controls = [...menuRef.current.querySelectorAll('button:not(:disabled)')]
      if (!controls.length) return
      const activeIndex = controls.indexOf(document.activeElement)
      let nextIndex = activeIndex
      if (event.key === 'Home') nextIndex = 0
      else if (event.key === 'End') nextIndex = controls.length - 1
      else if (event.key === 'ArrowDown') nextIndex = (activeIndex + 1 + controls.length) % controls.length
      else if (event.key === 'ArrowUp') nextIndex = (activeIndex <= 0 ? controls.length : activeIndex) - 1
      event.preventDefault()
      controls[nextIndex]?.focus()
    }
    window.addEventListener('resize', placeMenu)
    window.addEventListener('scroll', placeMenu, true)
    document.addEventListener('pointerdown', dismiss)
    document.addEventListener('keydown', keydown)
    return () => {
      window.cancelAnimationFrame(raf)
      window.removeEventListener('resize', placeMenu)
      window.removeEventListener('scroll', placeMenu, true)
      document.removeEventListener('pointerdown', dismiss)
      document.removeEventListener('keydown', keydown)
    }
  }, [open, placeMenu])

  return <>
    <button
      ref={triggerRef}
      type="button"
      aria-haspopup="menu"
      aria-expanded={open}
      aria-label={label}
      onClick={() => setOpen((value) => !value)}
      className={trigger ? 'rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold-500' : 'rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'}
    >
      {trigger ?? '•••'}
    </button>
    {open && createPortal(
      <div ref={menuRef} role="menu" aria-label={label} style={{ position: 'fixed', top: position.top, left: position.left, width: MENU_WIDTH, zIndex: 100 }} className="rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
        {enabledItems.map((item) => <button key={item.key ?? item.label} role="menuitem" type="button" disabled={item.disabled} onClick={() => { setOpen(false); triggerRef.current?.focus(); item.onSelect?.() }} className={`flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm disabled:opacity-50 ${item.danger ? 'text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50' : 'text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800'}`}>
          <span>{item.label}</span>
          {item.badge != null && Number(item.badge) > 0 && <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-semibold tabular-nums text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">{item.badge}</span>}
        </button>)}
      </div>,
      document.body,
    )}
  </>
}
