import { createContext, useCallback, useContext, useEffect, useState } from 'react'

const ToastContext = createContext(null)
const VARIANT_STYLES = {
  success: 'border-emerald-500 bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200',
  error: 'border-red-500 bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-200',
  info: 'border-indigo-500 bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-200',
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const dismiss = useCallback((id) => setToasts((current) => current.filter((toast) => toast.id !== id)), [])
  const showToast = useCallback((message, variant = 'info', duration = 4000, action = null) => {
    const id = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
    const safeMessage = typeof message === 'string' ? message : 'Something went wrong.'
    setToasts((current) => [...current, { id, message: safeMessage, variant, action }])
    if (duration) window.setTimeout(() => dismiss(id), duration)
    return id
  }, [dismiss])

  useEffect(() => {
    const handleExpired = () => showToast('Your session expired. Please log in again.', 'info', 7000)
    window.addEventListener('talentmatch:session-expired', handleExpired)
    return () => window.removeEventListener('talentmatch:session-expired', handleExpired)
  }, [showToast])

  return <ToastContext.Provider value={{ showToast, dismiss }}>
    {children}
    <div aria-label="Notifications" className="fixed bottom-4 right-4 z-50 flex w-96 flex-col gap-2">
      {toasts.map((toast) => <div key={toast.id} role={toast.variant === 'error' ? 'alert' : 'status'} aria-live={toast.variant === 'error' ? 'assertive' : 'polite'} className={`flex items-start justify-between gap-3 animate-toast rounded-xl border-l-4 px-4 py-3 shadow-lg ring-1 ring-black/5 ${VARIANT_STYLES[toast.variant] ?? VARIANT_STYLES.info}`}>
        <p className="flex-1 text-sm">{toast.message}</p>
        {toast.action && <button type="button" onClick={() => { toast.action.onClick?.(); dismiss(toast.id) }} className="shrink-0 text-sm font-semibold text-indigo-700 underline dark:text-indigo-300">{toast.action.label ?? 'Undo'}</button>}
        <button type="button" onClick={() => dismiss(toast.id)} aria-label="Dismiss notification" className="text-sm leading-none opacity-60 hover:opacity-100">×</button>
      </div>)}
    </div>
  </ToastContext.Provider>
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used within a ToastProvider')
  return context
}
