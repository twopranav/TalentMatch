import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/ui/Toast'
import Spinner from '../components/ui/Spinner'
import ThemeToggle from '../components/ui/ThemeToggle'

export default function Register() {
  const { register } = useAuth()
  const { showToast } = useToast()
  const navigate = useNavigate()

  const [form, setForm] = useState({
    email: '',
    password: '',
    full_name: '',
    phone: '',
    wantsRecruiter: false,
  })
  const [submitting, setSubmitting] = useState(false)

  const set = (field) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm((f) => ({ ...f, [field]: value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await register({
        email: form.email,
        password: form.password,
        full_name: form.full_name || null,
        phone: form.phone || null,
        role: form.wantsRecruiter ? 'recruiter' : 'user',
      })
      showToast(
        form.wantsRecruiter
          ? 'Account created. Recruiter access needs admin approval — log in now with standard access in the meantime.'
          : 'Account created. You can log in now.',
        'success',
      )
      navigate('/login')
    } catch (err) {
      const message =
        err.response?.status === 400
          ? err.response?.data?.detail || 'That email is already registered.'
          : 'Could not create the account. Please try again.'
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
          Create your TalentMatch account
        </h1>

        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300" htmlFor="email">
          Email
        </label>
        <input
          id="email"
          type="email"
          required
          value={form.email}
          onChange={set('email')}
          className="mb-4 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500"
        />

        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          type="password"
          required
          minLength={8}
          value={form.password}
          onChange={set('password')}
          className="mb-4 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500"
        />

        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300" htmlFor="full_name">
          Full name
        </label>
        <input
          id="full_name"
          type="text"
          value={form.full_name}
          onChange={set('full_name')}
          className="mb-4 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500"
        />

        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300" htmlFor="phone">
          Phone
        </label>
        <input
          id="phone"
          type="tel"
          value={form.phone}
          onChange={set('phone')}
          className="mb-4 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500"
        />

        <label className="mb-6 flex items-start gap-2 text-sm text-slate-600 dark:text-slate-300">
          <input
            type="checkbox"
            checked={form.wantsRecruiter}
            onChange={set('wantsRecruiter')}
            className="mt-0.5 h-4 w-4 rounded border-slate-300 dark:border-slate-600"
          />
          <span>I'm signing up as a recruiter (requires admin approval — standard access until then)</span>
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="flex w-full items-center justify-center gap-2 rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600"
        >
          {submitting ? <Spinner size="sm" label="Creating account" /> : 'Create account'}
        </button>

        <p className="mt-4 text-center text-xs text-slate-500 dark:text-slate-400">
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-slate-700 underline hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100">
            Log in
          </Link>
        </p>
      </form>
    </div>
  )
}