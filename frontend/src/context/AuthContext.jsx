// frontend/src/context/AuthContext.jsx
import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react'
import apiClient, { hasSessionCookie } from '../api/client'

const AuthContext = createContext(null)

// Tabs tell each other about logins and logouts, like a normal website: log out
// in one tab and the others drop to the login page; log in and a tab sitting on
// the login page moves on.
const CHANNEL_NAME = 'talentmatch-auth'

function openChannel() {
  try {
    return typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(CHANNEL_NAME) : null
  } catch {
    return null
  }
}

function normalizeProfile(profile, current) {
  if (!profile) return current
  return {
    ...current,
    ...profile,
    id: profile.id ?? current?.id,
    role: profile.role ?? current?.role,
    name: profile.full_name ?? profile.name ?? current?.name ?? '',
    email: profile.email ?? current?.email ?? '',
    avatar_url: profile.avatar_url ?? current?.avatar_url ?? null,
    requested_role: profile.requested_role ?? current?.requested_role ?? null,
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // True until we know whether the cookies amount to a live login. Without it a
  // page reload would flash the login screen before /users/me answers.
  const [loading, setLoading] = useState(() => hasSessionCookie())
  const channelRef = useRef(null)

  const clearLocalSession = useCallback(() => setUser(null), [])

  const loadUser = useCallback(async () => {
    try {
      const { data } = await apiClient.get('/users/me')
      setUser((current) => normalizeProfile(data, current))
      return true
    } catch {
      return false
    }
  }, [])

  useEffect(() => {
    let active = true
    if (!hasSessionCookie()) {
      setLoading(false)
      return undefined
    }
    loadUser().finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [loadUser])

  useEffect(() => {
    const handleUnauthorized = () => clearLocalSession()
    window.addEventListener('talentmatch:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('talentmatch:unauthorized', handleUnauthorized)
  }, [clearLocalSession])

  useEffect(() => {
    const channel = openChannel()
    channelRef.current = channel
    if (!channel) return undefined
    channel.onmessage = (event) => {
      if (event.data === 'logout') setUser(null)
      else if (event.data === 'login') loadUser()
    }
    return () => { channel.close(); channelRef.current = null }
  }, [loadUser])

  const login = useCallback(async (email, password) => {
    const form = new URLSearchParams()
    form.append('username', email)
    form.append('password', password)
    // The response sets the session cookies; the token in its body is ignored.
    await apiClient.post('/auth/login', form, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
    const { data } = await apiClient.get('/users/me')
    const nextUser = normalizeProfile(data, null)
    setUser(nextUser)
    setLoading(false)
    channelRef.current?.postMessage('login')
    return nextUser
  }, [])

  const register = useCallback(async (payload) => {
    const { data } = await apiClient.post('/auth/register', payload)
    return data
  }, [])

  const logout = useCallback(async () => {
    clearLocalSession()
    channelRef.current?.postMessage('logout')
    try { await apiClient.post('/auth/logout') } catch { /* local logout is authoritative */ }
  }, [clearLocalSession])

  const refreshProfile = useCallback(async () => {
    const { data } = await apiClient.get('/users/me')
    setUser((current) => normalizeProfile(data, current))
    return data
  }, [])

  return (
    <AuthContext.Provider value={{ user, setUser, isAuthenticated: !!user, loading, login, register, logout, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
