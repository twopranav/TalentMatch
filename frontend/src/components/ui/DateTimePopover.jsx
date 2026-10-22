import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import Button from './Button'

// Themed replacement for the browser's native date/time picker. Renders in a
// portal (so table overflow can't clip it), anchored under `anchor`, with
// Save / Cancel inside the popover itself.
//   value   'YYYY-MM-DDTHH:mm' (local time) or '' for "nothing chosen yet"
//   onSave  receives 'YYYY-MM-DDTHH:mm'; may return a promise
//   onClose called on Cancel, Escape and outside click

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const HOURS = Array.from({ length: 24 }, (_, i) => i)

const pad = (n) => String(n).padStart(2, '0')
const dateKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const parseKey = (key) => { const [y, m, d] = key.split('-').map(Number); return new Date(y, m - 1, d) }

function parseValue(value) {
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})/.exec(value || '')
  if (match) return { date: match[1], hour: Number(match[2]), minute: Number(match[3]) }
  return { date: dateKey(new Date()), hour: 10, minute: 0 }
}

const CHEVRONS = {
  left: 'M12.5 4.5 7 10l5.500 5.500',
  right: 'M7.5 4.5 13 10l-5.500 5.500',
  down: 'M5 7.500 10 12.500 15 7.500',
  up: 'M5 12.500 10 7.500 15 12.500',
}

function Chevron({ dir, className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 20 20" className={className} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={CHEVRONS[dir]} />
    </svg>
  )
}

const HEADER_BTN = 'flex items-center gap-1 rounded-lg py-1 pl-2 pr-1.5 text-sm font-semibold text-slate-800 transition hover:bg-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-slate-100 dark:hover:bg-slate-800'
const NAV_BTN = 'flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'

export default function DateTimePopover({ anchor, value, title = 'Schedule', subtitle, onSave, onClose }) {
  const [init] = useState(() => parseValue(value))
  const [selected, setSelected] = useState(init.date)
  const [hour, setHour] = useState(init.hour)
  const [minute, setMinute] = useState(init.minute)
  const [view, setView] = useState(() => { const d = parseKey(init.date); return { y: d.getFullYear(), m: d.getMonth() } })
  const [pos, setPos] = useState({ top: -9999, left: -9999 })
  const [saving, setSaving] = useState(false)
  // Opens on the month/year step; picking a month reveals the day grid + time lists.
  const [step, setStep] = useState('months')
  const panelRef = useRef(null)
  const keyboardNav = useRef(false)
  const todayKey = dateKey(new Date())

  const minutes = useMemo(() => {
    const base = Array.from({ length: 12 }, (_, i) => i * 5)
    return base.includes(init.minute) ? base : [...base, init.minute].sort((a, b) => a - b)
  }, [init.minute])

  const cells = useMemo(() => {
    const offset = (new Date(view.y, view.m, 1).getDay() + 6) % 7 // Monday-first
    return Array.from({ length: 42 }, (_, i) => new Date(view.y, view.m, 1 - offset + i))
  }, [view])

  // Anchor under the trigger; flip above if there is no room; keep on screen.
  useLayoutEffect(() => {
    const place = () => {
      const panel = panelRef.current
      if (!anchor || !panel) return
      const r = anchor.getBoundingClientRect()
      const w = panel.offsetWidth
      const h = panel.offsetHeight
      let top = r.bottom + 8
      if (top + h > window.innerHeight - 8 && r.top - h - 8 > 8) top = r.top - h - 8
      top = Math.max(8, Math.min(top, window.innerHeight - h - 8))
      const left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8))
      setPos((prev) => (prev.top === top && prev.left === left ? prev : { top, left }))
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [anchor, step])

  // Whenever a step appears: centre the chosen hour/minute in their lists and
  // focus the chosen day (or the viewed month on the month step).
  useLayoutEffect(() => {
    const panel = panelRef.current
    if (!panel) return
    if (step === 'days') {
      panel.querySelectorAll('[data-time-list]').forEach((list) => {
        const btn = list.querySelector('[aria-selected="true"]')
        if (btn) list.scrollTop = btn.offsetTop - list.clientHeight / 2 + btn.offsetHeight / 2
      })
      panel.querySelector('[data-selected-day]')?.focus({ preventScroll: true })
    } else {
      panel.querySelector('[data-selected-month]')?.focus({ preventScroll: true })
    }
  }, [step])

  useEffect(() => {
    const onDown = (e) => {
      if (panelRef.current?.contains(e.target) || anchor?.contains(e.target)) return
      onClose()
    }
    const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [anchor, onClose])

  // Keep keyboard focus on the chosen day after arrow-key moves.
  useEffect(() => {
    if (!keyboardNav.current) return
    keyboardNav.current = false
    panelRef.current?.querySelector('[data-selected-day], [data-selected-month]')?.focus({ preventScroll: true })
  }, [selected, view])

  const goMonth = (delta) => setView((v) => { const d = new Date(v.y, v.m + delta, 1); return { y: d.getFullYear(), m: d.getMonth() } })
  const goYear = (delta) => setView((v) => ({ ...v, y: v.y + delta }))
  const chooseMonth = (m) => { setView((v) => ({ y: v.y, m })); setStep('days') }
  const pickDate = (d) => { setSelected(dateKey(d)); if (d.getMonth() !== view.m || d.getFullYear() !== view.y) setView({ y: d.getFullYear(), m: d.getMonth() }) }
  const goToday = () => { pickDate(new Date()); setStep('days') }

  const onMonthKeyDown = (e) => {
    const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -3, ArrowDown: 3 }[e.key]
    if (!delta) return
    e.preventDefault()
    keyboardNav.current = true
    goMonth(delta)
  }

  const onGridKeyDown = (e) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key]
    if (!step) return
    e.preventDefault()
    const d = parseKey(selected)
    d.setDate(d.getDate() + step)
    keyboardNav.current = true
    pickDate(d)
  }

  const handleSave = async () => {
    setSaving(true)
    try { await onSave(`${selected}T${pad(hour)}:${pad(minute)}`) } finally { setSaving(false) }
  }

  const chosen = parseKey(selected)
  const summary = `${DAY_NAMES[chosen.getDay()]}, ${chosen.getDate()} ${MONTHS[chosen.getMonth()].slice(0, 3)} ${chosen.getFullYear()} · ${pad(hour)}:${pad(minute)}`

  const dayClass = (d, isSelected) => {
    const outside = d.getMonth() !== view.m
    const base = 'flex h-9 w-9 items-center justify-center rounded-lg text-sm tabular-nums transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500'
    if (isSelected) return `${base} bg-indigo-600 font-semibold text-white shadow-sm`
    if (dateKey(d) === todayKey) return `${base} font-semibold text-gold-700 ring-1 ring-gold-400/70 hover:bg-indigo-50 dark:text-gold-300 dark:hover:bg-indigo-950/60`
    if (outside) return `${base} text-slate-300 hover:bg-slate-100 dark:text-slate-600 dark:hover:bg-slate-800`
    return `${base} text-slate-700 hover:bg-indigo-50 dark:text-slate-200 dark:hover:bg-indigo-950/60`
  }

  const timeClass = (isSelected) => `flex h-8 w-full items-center justify-center rounded-lg text-sm tabular-nums transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${isSelected ? 'bg-indigo-600 font-semibold text-white shadow-sm' : 'text-slate-700 hover:bg-indigo-50 dark:text-slate-200 dark:hover:bg-indigo-950/60'}`

  const today = new Date()
  const monthClass = (m) => {
    const base = 'flex h-12 items-center justify-center rounded-xl text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500'
    if (m === view.m) return `${base} bg-indigo-600 font-semibold text-white shadow-sm`
    if (view.y === today.getFullYear() && m === today.getMonth()) return `${base} font-semibold text-gold-700 ring-1 ring-gold-400/70 hover:bg-indigo-50 dark:text-gold-300 dark:hover:bg-indigo-950/60`
    return `${base} font-medium text-slate-700 hover:bg-indigo-50 dark:text-slate-200 dark:hover:bg-indigo-950/60`
  }

  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-label={title}
      style={{ top: pos.top, left: pos.left }}
      className="fixed z-60 w-102 max-w-[calc(100vw-1rem)] rounded-2xl border border-slate-200 border-t-gold-300/80 bg-white shadow-2xl dark:border-slate-700 dark:border-t-gold-400/50 dark:bg-slate-900"
    >
      <div className="flex items-start justify-between gap-3 px-4 pt-3.5">
        <div className="min-w-0">
          <p className="font-display text-xl font-semibold leading-tight text-slate-900 dark:text-slate-100">{title}</p>
          {subtitle && <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>}
        </div>
        <button type="button" onClick={goToday} className="mt-1 shrink-0 text-xs font-semibold text-indigo-700 hover:underline dark:text-indigo-300">Today</button>
      </div>

      {step === 'months' ? (
        <div className="min-h-78 px-4 pb-3 pt-2">
          <div className="mb-3 flex items-center justify-between">
            <button type="button" onClick={() => setStep('days')} aria-label="Back to the day picker" className={HEADER_BTN}>
              {view.y}<Chevron dir="up" className="h-3.5 w-3.5" />
            </button>
            <div className="flex items-center">
              <button type="button" aria-label="Previous year" onClick={() => goYear(-1)} className={NAV_BTN}><Chevron dir="left" /></button>
              <button type="button" aria-label="Next year" onClick={() => goYear(1)} className={NAV_BTN}><Chevron dir="right" /></button>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2" role="grid" aria-label={`Months of ${view.y}`} onKeyDown={onMonthKeyDown}>
            {MONTHS.map((name, m) => (
              <button
                key={name}
                type="button"
                tabIndex={m === view.m ? 0 : -1}
                data-selected-month={m === view.m ? '' : undefined}
                aria-label={`${name} ${view.y}`}
                onClick={() => chooseMonth(m)}
                className={monthClass(m)}
              >
                {name.slice(0, 3)}
              </button>
            ))}
          </div>
        </div>
      ) : (
      <div className="flex gap-3 px-4 pb-3 pt-2">
        <div className="min-w-0">
          <div className="mb-1 flex items-center justify-between">
            <button type="button" onClick={() => setStep('months')} aria-label="Choose month and year" className={`${HEADER_BTN} -ml-2`}>
              {MONTHS[view.m]} {view.y}<Chevron dir="down" className="h-3.5 w-3.5" />
            </button>
            <div className="flex items-center">
              <button type="button" aria-label="Previous month" onClick={() => goMonth(-1)} className={NAV_BTN}><Chevron dir="left" /></button>
              <button type="button" aria-label="Next month" onClick={() => goMonth(1)} className={NAV_BTN}><Chevron dir="right" /></button>
            </div>
          </div>
          <div className="grid grid-cols-7 text-center">
            {WEEKDAYS.map((w) => <span key={w} className="py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">{w}</span>)}
          </div>
          <div className="grid grid-cols-7" role="grid" onKeyDown={onGridKeyDown}>
            {cells.map((d) => {
              const key = dateKey(d)
              const isSelected = key === selected
              return (
                <button
                  key={key}
                  type="button"
                  tabIndex={isSelected ? 0 : -1}
                  data-selected-day={isSelected ? '' : undefined}
                  aria-label={`${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`}
                  aria-pressed={isSelected}
                  onClick={() => pickDate(d)}
                  className={dayClass(d, isSelected)}
                >
                  {d.getDate()}
                </button>
              )
            })}
          </div>
        </div>

        <div className="flex w-28 shrink-0 flex-col border-l border-slate-100 pl-3 dark:border-slate-800">
          <p className="py-1 text-center text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">Hour · Min</p>
          <div className="flex h-66 gap-1.5">
            <div data-time-list role="listbox" aria-label="Hour" className="relative flex-1 space-y-0.5 overflow-y-auto">
              {HOURS.map((h) => <button key={h} type="button" role="option" aria-selected={h === hour} onClick={() => setHour(h)} className={timeClass(h === hour)}>{pad(h)}</button>)}
            </div>
            <div data-time-list role="listbox" aria-label="Minute" className="relative flex-1 space-y-0.5 overflow-y-auto">
              {minutes.map((m) => <button key={m} type="button" role="option" aria-selected={m === minute} onClick={() => setMinute(m)} className={timeClass(m === minute)}>{pad(m)}</button>)}
            </div>
          </div>
        </div>
      </div>
      )}

      <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-4 py-3 dark:border-slate-800">
        <p className="min-w-0 truncate text-xs font-medium text-slate-600 dark:text-slate-300">{step === 'months' ? 'Pick a month to continue' : summary}</p>
        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm" variant="subtle" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button size="sm" onClick={handleSave} disabled={saving || step === 'months'}>{saving ? 'Saving…' : 'Save'}</Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}