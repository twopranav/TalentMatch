// Google-style page links: Previous, a sliding window of up to 10 page
// numbers, Next. When the window doesn't include the first/last page, a
// shortcut to it is shown with an ellipsis.
const WINDOW = 10

const base = 'min-w-[2rem] rounded px-2 py-1 text-center text-xs font-medium transition'
const idle = 'text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
const off = 'cursor-not-allowed text-slate-300 dark:text-slate-600'

export default function Pagination({ page, totalPages, onPageChange, disabled = false }) {
  if (totalPages <= 1) return null

  const start = Math.max(1, Math.min(page - Math.floor(WINDOW / 2) + 1, totalPages - WINDOW + 1))
  const end = Math.min(totalPages, start + WINDOW - 1)
  const pages = []
  for (let p = start; p <= end; p += 1) pages.push(p)

  const go = (p) => {
    if (!disabled && p >= 1 && p <= totalPages && p !== page) onPageChange(p)
  }

  return (
    <nav aria-label="Pagination" className="mt-3 flex flex-wrap items-center justify-center gap-1">
      <button type="button" onClick={() => go(page - 1)} disabled={disabled || page === 1} className={`${base} ${page === 1 ? off : idle}`}>
        ‹ Previous
      </button>
      {start > 1 && (
        <>
          <button type="button" onClick={() => go(1)} disabled={disabled} className={`${base} ${idle}`}>1</button>
          {start > 2 && <span className="px-1 text-xs text-slate-400">…</span>}
        </>
      )}
      {pages.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => go(p)}
          disabled={disabled}
          aria-current={p === page ? 'page' : undefined}
          className={`${base} tabular-nums ${p === page ? 'bg-indigo-600 text-white dark:bg-indigo-500' : idle}`}
        >
          {p}
        </button>
      ))}
      {end < totalPages && (
        <>
          {end < totalPages - 1 && <span className="px-1 text-xs text-slate-400">…</span>}
          <button type="button" onClick={() => go(totalPages)} disabled={disabled} className={`${base} ${idle}`}>{totalPages}</button>
        </>
      )}
      <button type="button" onClick={() => go(page + 1)} disabled={disabled || page === totalPages} className={`${base} ${page === totalPages ? off : idle}`}>
        Next ›
      </button>
    </nav>
  )
}
