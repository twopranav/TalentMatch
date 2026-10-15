export default function PageHeader({ eyebrow, title, description, action, meta, className = '' }) {
  return (
    <div className={`mb-8 flex items-end justify-between gap-6 ${className}`}>
      <div className="min-w-0">
        {eyebrow && <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-indigo-600 dark:text-indigo-300">{eyebrow}</p>}
        <h1 className="font-display text-4xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">{title}</h1>
        {description && <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500 dark:text-slate-400">{description}</p>}
        {meta && <div className="mt-3">{meta}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}
