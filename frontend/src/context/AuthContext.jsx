// frontend/src/context/AuthContext.jsx
import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import apiClient from '../api/client'
import { decodeJwtPayload, isTokenExpired } from '../utils/jwt'

const AuthContext = createContext(null)

function readStoredUser() {
  const token = localStorage.getItem('access_token')
  if (!token) return null
  const payload = decodeJwtPayload(token)
  if (!payload || isTokenExpired(payload)) { localStorage.removeItem('access_token'); return null }
  return { id: payload.sub, role: payload.role, token, name: payload.name ?? payload.full_name ?? '', email: payload.email ?? '', avatar_url: payload.avatar_url ?? null, requested_role: payload.requested_role ?? null }
}

function normalizeProfile(profile, current) {
  if (!profile) return current
  return {
    ...current,
    ...profile,
    id: profile.id ?? current?.id,
    role: profile.role ?? current?.role,
    name: profile.name ?? profile.full_name ?? current?.name ?? '',
    email: profile.email ?? current?.email ?? '',
    avatar_url: profile.avatar_url ?? current?.avatar_url ?? null,
    requested_role: profile.requested_role ?? current?.requested_role ?? null,
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(readStoredUser)
  const clearLocalSession = useCallback(() => {
    localStorage.removeItem('access_token')
    setUser(null)
  }, [])

  useEffect(() => {
    const handleUnauthorized = () => clearLocalSession()
    window.addEventListener('talentmatch:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('talentmatch:unauthorized', handleUnauthorized)
  }, [clearLocalSession])

  useEffect(() => {
    if (!user?.token) return
    let active = true
    apiClient.get('/users/me').then(({ data }) => {
      if (active) setUser((current) => normalizeProfile(data, current))
    }).catch(() => {})
    return () => { active = false }
  }, [user?.token])

  const login = useCallback(async (email, password) => {
    const form = new URLSearchParams()
    form.append('username', email)
    form.append('password', password)
    const { data } = await apiClient.post('/auth/login', form, { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } })
    localStorage.setItem('access_token', data.access_token)
    const payload = decodeJwtPayload(data.access_token)
    const nextUser = { id: payload?.sub, role: payload?.role, token: data.access_token, name: payload?.name ?? payload?.full_name ?? '', email: payload?.email ?? email, avatar_url: payload?.avatar_url ?? null, requested_role: payload?.requested_role ?? null }
    setUser(nextUser)
    try {
      const profile = await apiClient.get('/users/me')
      setUser((current) => normalizeProfile(profile.data, current))
    } catch { /* some installations omit /users/me profile extras */ }
    return nextUser
  }, [])

  const register = useCallback(async (payload) => {
    const { data } = await apiClient.post('/auth/register', payload)
    return data
  }, [])

  const logout = useCallback(async () => {
    const token = localStorage.getItem('access_token')
    clearLocalSession()
    if (token) {
      try { await apiClient.post('/auth/logout') } catch { /* local logout is authoritative */ }
    }
  }, [clearLocalSession])

  const refreshProfile = useCallback(async () => {
    const { data } = await apiClient.get('/users/me')
    setUser((current) => normalizeProfile(data, current))
    return data
  }, [])

  return <AuthContext.Provider value={{ user, setUser, isAuthenticated: !!user, login, register, logout, refreshProfile }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
