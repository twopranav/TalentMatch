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
    confirmPassword: '',
    full_name: '',
    phone: '',
    wantsRecruiter: false,
  })
  const [submitting, setSubmitting] = useState(false)

  const set = (field) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm((f) => ({ ...f, [field]: value }))
  }

  // Live check — evaluated on every render, not just on submit, so the
  // message appears the instant the second field diverges from the first.
  const passwordsMismatch = form.confirmPassword.length > 0 && form.password !== form.confirmPassword
  // Mirrors the backend's rule (schemas/user.py::_validate_password_strength):
  // at least 8 chars, with at least one letter and one number.
  const passwordTooWeak =
    form.password.length > 0 &&
    (form.password.length < 8 || !/[A-Za-z]/.test(form.password) || !/[0-9]/.test(form.password))
  const canSubmit =
    form.password.length > 0 && form.confirmPassword.length > 0 && !passwordsMismatch && !passwordTooWeak

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!canSubmit) return
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
      const status = err.response?.status
      const detail = err.response?.data?.detail
      let message = 'Could not create the account. Please try again.'
      if (status === 400) {
        message = detail || 'That email is already registered.'
      } else if (status === 422) {
        // FastAPI validation errors: detail is a list of {msg, loc, ...}.
        message = Array.isArray(detail) ? detail.map((d) => d.msg).join(' ') : detail || message
      }
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
          "linear-gradient(to bottom right, rgba(15,23,42,0.65), rgba(15,23,42,0.75)), url('https://images.unsplash.com/photo-1542744173-8e7e53415bb0?auto=format&fit=crop&w=2000&q=80')",
      }}
    >
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>

      <div className="flex w-full max-w-sm flex-col items-center">
        <div className="animate-slide-down mb-6 select-none text-center">
          <span className="text-3xl font-bold tracking-tight text-white drop-shadow-lg">
            Talent<span className="text-slate-300">Match</span>
          </span>
        </div>

        <form
          onSubmit={handleSubmit}
          className="animate-slide-down-delay w-full rounded-xl border border-white/40 bg-white/40 p-8 shadow-2xl backdrop-blur-xl dark:border-slate-700/50 dark:bg-slate-900/55"
        >
          <h1 className="mb-6 text-lg font-semibold text-slate-900 dark:text-slate-100">
            Create account
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
          className="mb-4 w-full rounded-lg border border-slate-400/70 bg-white/80 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500"
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
          aria-invalid={passwordTooWeak}
          aria-describedby="password-hint"
          className={`mb-1 w-full rounded-lg border bg-white/80 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 dark:bg-slate-800 dark:text-slate-100 ${
            passwordTooWeak
              ? 'border-red-400 focus:ring-red-400 dark:border-red-500 dark:focus:ring-red-500'
              : 'border-slate-400/70 focus:ring-slate-400 dark:border-slate-700 dark:focus:ring-slate-500'
          }`}
        />
        <p
          id="password-hint"
          className={`mb-4 min-h-4 text-xs font-medium ${
            passwordTooWeak ? 'text-red-600 dark:text-red-400' : 'text-slate-400 dark:text-slate-500'
          }`}
        >
          At least 8 characters, with a letter and a number
        </p>

        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300" htmlFor="confirm_password">
          Confirm password
        </label>
        <input
          id="confirm_password"
          type="password"
          required
          minLength={8}
          value={form.confirmPassword}
          onChange={set('confirmPassword')}
          aria-invalid={passwordsMismatch}
          aria-describedby={passwordsMismatch ? 'confirm-password-error' : undefined}
          className={`mb-1 w-full rounded-lg border bg-white/80 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 dark:bg-slate-800 dark:text-slate-100 ${
            passwordsMismatch
              ? 'border-red-400 focus:ring-red-400 dark:border-red-500 dark:focus:ring-red-500'
              : 'border-slate-400/70 focus:ring-slate-400 dark:border-slate-700 dark:focus:ring-slate-500'
          }`}
        />
        {/* Reserve the line even when empty so the layout doesn't jump
            as the message appears/disappears. */}
        <p
          id="confirm-password-error"
          className={`mb-4 min-h-4 text-xs font-medium text-red-600 dark:text-red-400 ${passwordsMismatch ? '' : 'invisible'}`}
        >
          Passwords don't match
        </p>

        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300" htmlFor="full_name">
          Full name
        </label>
        <input
          id="full_name"
          type="text"
          value={form.full_name}
          onChange={set('full_name')}
          className="mb-4 w-full rounded-lg border border-slate-400/70 bg-white/80 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500"
        />

        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300" htmlFor="phone">
          Phone
        </label>
        <input
          id="phone"
          type="tel"
          value={form.phone}
          onChange={set('phone')}
          className="mb-4 w-full rounded-lg border border-slate-400/70 bg-white/80 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500"
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
          disabled={submitting || !canSubmit}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-slate-800 shadow-md transition-colors px-4 py-2 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-60 dark:bg-slate-700 dark:hover:bg-slate-600"
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
    </div>
  )
} 