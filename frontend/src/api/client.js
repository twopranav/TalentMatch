import axios from 'axios'

const apiClient = axios.create({ baseURL: '/api' })
let expiryEventSent = false

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

apiClient.interceptors.response.use(
  (response) => {
    if (response.config?.url?.includes('/auth/login')) expiryEventSent = false
    return response
  },
  (error) => {
    const status = error.response?.status
    const url = error.config?.url ?? ''
    const hadToken = !!localStorage.getItem('access_token')
    if (status === 401 && hadToken && !url.includes('/auth/login') && !url.includes('/auth/register')) {
      if (!expiryEventSent) {
        expiryEventSent = true
        if (window.location.pathname !== '/login') {
          const path = `${window.location.pathname}${window.location.search}${window.location.hash}`
          if (!path.startsWith('/login')) sessionStorage.setItem('talentmatch:returnTo', path)
        }
        window.dispatchEvent(new CustomEvent('talentmatch:unauthorized'))
        window.dispatchEvent(new CustomEvent('talentmatch:session-expired'))
        window.dispatchEvent(new CustomEvent('talentmatch:navigate-login'))
      }
    }
    return Promise.reject(error)
  },
)

export default apiClient
