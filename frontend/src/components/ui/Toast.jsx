import { createContext, useCallback, useContext, useState } from 'react'

const ToastContext = createContext(null)

const VARIANT_STYLES = {
  success: 'border-emerald-600 bg-emerald-50 text-emerald-900',
  error: 'border-red-600 bg-red-50 text-red-900',
  info: 'border-slate-600 bg-slate-50 text-slate-900',
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((t) => t.id !== id))
  }, [])

  const showToast = useCallback(
    (message, variant = 'info', duration = 4000) => {
      const id = crypto.randomUUID()
      setToasts((current) => [...current, { id, message, variant }])
      if (duration) {
        setTimeout(() => dismiss(id), duration)
      }
    },
    [dismiss]
  )

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="alert"
            className={`flex items-start justify-between gap-3 rounded border-l-4 px-4 py-3 shadow-md ${VARIANT_STYLES[toast.variant]}`}
          >
            <p className="text-sm">{toast.message}</p>
            <button
              onClick={() => dismiss(toast.id)}
              aria-label="Dismiss"
              className="text-sm leading-none opacity-60 hover:opacity-100"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}