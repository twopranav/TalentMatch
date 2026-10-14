import { Link } from 'react-router-dom'
export default function NotFound() {
  return <div className="mx-auto max-w-3xl px-6 py-24 text-center"><p className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-600 dark:text-indigo-300">404 · Not found</p><h1 className="mt-3 text-5xl font-semibold text-slate-900 dark:text-slate-100">This page has moved</h1><p className="mx-auto mt-4 max-w-lg text-sm leading-6 text-slate-600 dark:text-slate-400">The link may be outdated, or the page may no longer exist.</p><Link className="mt-6 inline-flex items-center justify-center rounded-lg bg-indigo-700 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold-500" to="/">Return to overview</Link></div>
}
