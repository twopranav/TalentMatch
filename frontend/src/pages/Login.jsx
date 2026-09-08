// frontend/src/pages/Login.jsx
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/ui/Toast'
import Spinner from '../components/ui/Spinner'
import ThemeToggle from '../components/ui/ThemeToggle'

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
    <div className="relative flex min-h-screen items-center justify-center overflow-y-auto bg-slate-50 px-4 py-8 dark:bg-slate-950">
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>

      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900"
      >
        <h1 className="mb-6 text-lg font-semibold text-slate-900 dark:text-slate-100">
          Log in to TalentMatch
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
          className="mb-4 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500"
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
          className="mb-6 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500"
        />

        <button
          type="submit"
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600"
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
  )
}