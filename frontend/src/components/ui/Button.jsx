const VARIANTS = {
  primary: 'border border-indigo-600 bg-indigo-600 text-white shadow-sm hover:border-indigo-700 hover:bg-indigo-700 focus-visible:ring-indigo-500',
  secondary: 'border border-slate-200 bg-[#fbfaf7] text-slate-700 hover:border-indigo-200 hover:bg-white hover:text-indigo-700 focus-visible:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-indigo-800 dark:hover:bg-slate-800 dark:hover:text-indigo-300',
  subtle: 'border border-transparent bg-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus-visible:ring-indigo-500 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-white',
  danger: 'border border-red-600 bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-500',
}
const SIZES = { xs: 'px-2.5 py-1 text-xs', sm: 'px-3 py-1.5 text-xs', md: 'px-4 py-2.5 text-sm', lg: 'px-5 py-3 text-sm' }

export default function Button({ children, variant = 'primary', size = 'md', type = 'button', className = '', disabled = false, ...props }) {
  return <button type={type} disabled={disabled} className={`inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#fbfaf7] disabled:cursor-not-allowed disabled:opacity-50 dark:focus-visible:ring-offset-slate-950 ${VARIANTS[variant] ?? VARIANTS.primary} ${SIZES[size] ?? SIZES.md} ${className}`} {...props}>{children}</button>
}
