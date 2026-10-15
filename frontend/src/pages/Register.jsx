import emmveeLogo from '../assets/emmvee-logo.jpg'
import { SUB_COMPANIES } from '../utils/subCompany'
import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/ui/Toast'
import Spinner from '../components/ui/Spinner'
import ThemeToggle from '../components/ui/ThemeToggle'
import { Crest, CornerFan } from '../components/ui/Ornaments'

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
    role: 'user',
    sub_company: '',
  })
  const [submitting, setSubmitting] = useState(false)

  const set = (field) => (e) => {
    const value = e.target.value
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
    form.password.length > 0 && form.confirmPassword.length > 0 && !passwordsMismatch && !passwordTooWeak &&
    (form.role === 'user' || form.sub_company !== '')

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
        role: form.role,
        sub_company: form.role !== 'user' ? form.sub_company : null,
      })
      showToast(
        form.role !== 'user'
          ? `Account created. ${form.role === 'admin' ? 'Admin' : 'Recruiter'} access needs superuser approval — log in now with standard access in the meantime.`
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
          "linear-gradient(to bottom right, rgba(14,22,48,0.80), rgba(10,14,30,0.90)), url('https://images.unsplash.com/photo-1542744173-8e7e53415bb0?auto=format&fit=crop&w=2000&q=80')",
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
          <img src={emmveeLogo} alt="Emmvee" className="mx-auto mb-4 h-14 w-auto" />
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

        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300" htmlFor="role">
          Account type
        </label>
        <select id="role" value={form.role} onChange={set('role')} className="mb-1 w-full rounded-lg border border-slate-400/70 bg-white/80 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500">
          <option value="user">Candidate</option>
          <option value="recruiter">Recruiter (request)</option>
          <option value="admin">Admin (request)</option>
        </select>
        <p className="mb-4 min-h-4 text-xs text-slate-400 dark:text-slate-500">
          {form.role === 'user' ? 'Standard access.' : 'Needs superuser approval — standard access until then.'}
        </p>
        {form.role !== 'user' && (
          <div className="mb-6">
            <label htmlFor="sub_company" className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">Sub company</label>
            <select id="sub_company" value={form.sub_company} onChange={set('sub_company')} required className="w-full rounded-lg border border-slate-400/70 bg-white/80 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-slate-500">
              <option value="">Select your sub company</option>
              {SUB_COMPANIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        )}

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