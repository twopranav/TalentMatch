// frontend/src/pages/Login.jsx
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/ui/Toast'
import Spinner from '../components/ui/Spinner'
import ThemeToggle from '../components/ui/ThemeToggle'
import { Crest, CornerFan } from '../components/ui/Ornaments'

export default function Login() {
  const { login } = useAuth()
  const { showToast } = useToast()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await login(email, password)
      showToast('Logged in.', 'success')
    } catch (err) {
      const message =
        err.response?.status === 401
          ? 'Incorrect email or password.'
          : 'Could not log in. Please try again.'
      showToast(message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="relative flex min-h-screen items-center justify-center overflow-y-auto bg-slate-900 bg-cover bg-center px-4 py-8"
      style={{
        backgroundImage:
          "linear-gradient(to bottom right, rgba(14,22,48,0.80), rgba(10,14,30,0.90)), url('https://images.unsplash.com/photo-1573496130407-57329f01f769?auto=format&fit=crop&w=2000&q=80')",
      }}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <CornerFan className="absolute -bottom-20 -left-20 h-[26rem] w-[26rem] -scale-y-100 text-gold-400/35" />
        <CornerFan className="absolute -right-20 -top-20 h-[26rem] w-[26rem] -scale-x-100 text-gold-400/35" />
        <CornerFan className="absolute -bottom-40 -right-40 hidden h-[34rem] w-[34rem] -scale-100 text-gold-400/15 lg:block" />
        <CornerFan className="absolute -left-40 -top-40 hidden h-[34rem] w-[34rem] text-gold-400/15 lg:block" />
      </div>

      <div className="absolute right-4 top-4 z-10">
        <ThemeToggle />
      </div>

      <div className="flex w-full max-w-sm flex-col items-center">
        <div className="animate-slide-down relative mb-6 select-none text-center">
          <Crest className="mx-auto mb-3 h-14 w-14 drop-shadow-lg" />
          <span className="font-display text-5xl font-semibold tracking-wide text-white drop-shadow-lg">
            Talent<span className="text-gold-300">Match</span>
          </span>
          <span className="mx-auto mt-3 block h-px w-16 bg-linear-to-r from-transparent via-gold-400 to-transparent" />
        </div>

        <form
          onSubmit={handleSubmit}
          className="animate-slide-down-delay w-full rounded-2xl border border-white/50 border-t-gold-300/80 bg-white/90 p-8 shadow-2xl backdrop-blur-xl dark:border-white/10 dark:border-t-gold-400/50 dark:bg-slate-900/80"
        >
          <h1 className="mb-6 text-lg font-semibold text-slate-900 dark:text-slate-100">
            Log in
          </h1>

          <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mb-4 w-full rounded-lg border border-slate-400/70 bg-white/80 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500"
          />

          <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mb-6 w-full rounded-lg border border-slate-400/70 bg-white/80 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500"
          />

          <button
            type="submit"
            disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-slate-800 shadow-md transition-colors px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600"
          >
            {submitting ? <Spinner size="sm" label="Logging in" /> : 'Log in'}
          </button>

          <p className="mt-4 text-center text-xs text-slate-500 dark:text-slate-400">
            Don't have an account yet?{' '}
            <Link to="/register" className="font-medium text-slate-700 underline hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100">
              Create one
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}