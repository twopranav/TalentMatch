import { forwardRef } from 'react'

const variants = {
  primary: 'bg-indigo-700 text-white shadow-sm hover:bg-indigo-800 focus-visible:ring-2 focus-visible:ring-gold-500',
  secondary: 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800',
  subtle: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800',
  danger: 'bg-red-600 text-white hover:bg-red-700 focus-visible:ring-2 focus-visible:ring-gold-500',
}
const sizes = { sm: 'px-3 py-1.5 text-xs', md: 'px-4 py-2 text-sm', lg: 'px-5 py-2.5 text-sm' }

const Button = forwardRef(function Button({ variant = 'primary', size = 'md', className = '', type = 'button', ...props }, ref) {
  return <button ref={ref} type={type} className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant] ?? variants.primary} ${sizes[size] ?? sizes.md} ${className}`} {...props} />
})

export default Button
