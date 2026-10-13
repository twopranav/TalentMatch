// frontend/src/components/ui/Spinner.jsx
export default function Spinner({ size = 'md', label = 'Loading' }) {
  const sizes = {
    sm: 'h-4 w-4 border-2',
    md: 'h-6 w-6 border-2',
    lg: 'h-10 w-10 border-[3px]',
  }

  return (
    <div role="status" className="inline-flex items-center gap-2">
      <span
        className={`${sizes[size]} animate-spin rounded-full border-slate-300 border-t-gold-500 dark:border-slate-700 dark:border-t-gold-400`}
      />
      <span className="sr-only">{label}</span>
    </div>
  )
}