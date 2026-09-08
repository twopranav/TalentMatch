// frontend/src/context/AuthContext.jsx
import { createContext, useContext, useState, useCallback } from 'react'
import apiClient from '../api/client'
import { decodeJwtPayload, isTokenExpired } from '../utils/jwt'

const AuthContext = createContext(null)

function readStoredUser() {
  const token = localStorage.getItem('access_token')
  if (!token) return null

  const payload = decodeJwtPayload(token)
  if (!payload || isTokenExpired(payload)) {
    localStorage.removeItem('access_token')
    return null
  }

  return { id: payload.sub, role: payload.role, token }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(readStoredUser)

  const login = useCallback(async (email, password) => {
    const form = new URLSearchParams()
    form.append('username', email)
    form.append('password', password)

    const { data } = await apiClient.post('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })

    localStorage.setItem('access_token', data.access_token)
    const payload = decodeJwtPayload(data.access_token)
    setUser({ id: payload.sub, role: payload.role, token: data.access_token })
  }, [])

  // Registration never logs the account in automatically — the backend
  // doesn't return a token here (only UserRead), and a requested-recruiter
  // signup is still just a USER until an admin approves it. Send them to
  // /login so the flow is explicit either way.
  const register = useCallback(async (payload) => {
    const { data } = await apiClient.post('/auth/register', payload)
    return data
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    setUser(null)
  }, [])

  const value = {
    user,
    isAuthenticated: !!user,
    login,
    register,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}