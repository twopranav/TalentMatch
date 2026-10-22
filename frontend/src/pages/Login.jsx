import BrandLogo from '../components/ui/BrandLogo'
import { TalentMatchWordmark } from '../components/ui/TalentMatchMark'
// frontend/src/pages/Login.jsx
import { Link } from 'react-router-dom'
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/ui/Toast'
import Spinner from '../components/ui/Spinner'
import ThemeToggle from '../components/ui/ThemeToggle'
import Button from '../components/ui/Button'
import Field from '../components/ui/Field'
import { CornerFan } from '../components/ui/Ornaments'

export default function Login() {
  const { login } = useAuth()
  const { showToast } = useToast()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await login(email.trim(), password)
    } catch (err) {
      const message =
        err.response?.status === 401
          ? 'Incorrect email or password.'
          : err.response?.status === 403
            ? 'This account is not active yet. Contact an administrator.'
            : 'Could not log in. Please try again.'
      showToast(message, 'error')
    } finally {
      setSubmitting(false)
    }
  }

  // No remote background image: this is an internal tool and must render
  // identically on networks that block third-party hosts. The whole page
  // (not just the card) follows the light / dark theme via app-bg.
  return (
    <div className="app-bg relative flex min-h-screen items-center justify-center overflow-y-auto px-4 py-8">
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <CornerFan className="absolute -bottom-20 -left-20 h-[26rem] w-[26rem] -scale-y-100 text-gold-500/30 dark:text-gold-400/35" />
        <CornerFan className="absolute -right-20 -top-20 h-[26rem] w-[26rem] -scale-x-100 text-gold-500/30 dark:text-gold-400/35" />
        <CornerFan className="absolute -bottom-40 -right-40 hidden h-[34rem] w-[34rem] -scale-100 text-gold-500/15 dark:text-gold-400/15 lg:block" />
        <CornerFan className="absolute -left-40 -top-40 hidden h-[34rem] w-[34rem] text-gold-500/15 dark:text-gold-400/15 lg:block" />
      </div>

      <div className="absolute right-4 top-4 z-10"><ThemeToggle /></div>

      <div className="flex w-full max-w-sm flex-col items-center">
        <form onSubmit={handleSubmit} className="animate-slide-down-delay w-full rounded-2xl border border-white/50 border-t-gold-300/80 bg-white/90 p-8 shadow-2xl backdrop-blur-xl dark:border-white/10 dark:border-t-gold-400/50 dark:bg-slate-900/80">
          <BrandLogo className="mx-auto mb-5 h-20" />
          <h1 className="text-center text-2xl text-slate-900 dark:text-slate-100">Sign in</h1>
          <TalentMatchWordmark className="mb-6 mt-3" />

          <div className="space-y-4">
            <Field label="Email" id="email" type="email" required autoComplete="username" autoFocus value={email} onChange={(e) => setEmail(e.target.value)} />
            <div className="space-y-1.5">
              <Field label="Password" id="password" type={showPassword ? 'text' : 'password'} required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                <input type="checkbox" checked={showPassword} onChange={(e) => setShowPassword(e.target.checked)} />
                Show password
              </label>
            </div>
          </div>

          <Button type="submit" disabled={submitting} className="mt-6 w-full">
            {submitting ? <Spinner size="sm" label="Signing in" /> : 'Sign in'}
          </Button>

          <p className="mt-4 text-center text-xs text-slate-500 dark:text-slate-400">
            Don't have an account yet?{' '}
            <Link to="/register" className="font-semibold text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300">Create one</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
