import { useId } from 'react'

const controlClass = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-gold-400/50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100'

export default function Field({ label, id, hint, error, as = 'input', className = '', children, ...props }) {
  const generatedId = useId()
  const fieldId = id ?? generatedId
  const controlProps = {
    id: fieldId,
    'aria-invalid': error ? 'true' : undefined,
    'aria-describedby': [hint ? `${fieldId}-hint` : null, error ? `${fieldId}-error` : null].filter(Boolean).join(' ') || undefined,
    className: `${controlClass} ${className}`,
    ...props,
  }
  const control = as === 'textarea'
    ? <textarea {...controlProps}>{children}</textarea>
    : as === 'select'
      ? <select {...controlProps}>{children}</select>
      : <input {...controlProps} />
  return <div className="space-y-1.5">
    {label && <label htmlFor={fieldId} className="block text-sm font-medium text-slate-700 dark:text-slate-300">{label}</label>}
    {control}
    {hint && <p id={`${fieldId}-hint`} className="text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    {error && <p id={`${fieldId}-error`} role="alert" className="text-xs text-red-600 dark:text-red-400">{error}</p>}
  </div>
}
