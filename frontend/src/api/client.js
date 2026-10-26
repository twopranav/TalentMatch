import axios from 'axios'

// Login state lives in httpOnly cookies the browser sends by itself; nothing
// secret is stored where JavaScript (or an XSS bug) could read it. The one
// cookie the page can read is the CSRF token, which also tells us that a login
// exists at all.
export const CSRF_COOKIE = 'tm_csrf'
const SAFE_METHODS = new Set(['get', 'head', 'options'])
const AUTH_URLS = ['/auth/login', '/auth/register', '/auth/refresh', '/auth/logout']

export function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

export function hasSessionCookie() {
  return !!getCookie(CSRF_COOKIE)
}

function forgetSessionCookie() {
  document.cookie = `${CSRF_COOKIE}=; Max-Age=0; path=/`
}

const apiClient = axios.create({ baseURL: '/api', withCredentials: true })
// Same thing without the interceptors below, so a failing refresh can't recurse.
const bareClient = axios.create({ baseURL: '/api', withCredentials: true })

let expiryEventSent = false
let refreshPromise = null

// One refresh at a time per tab; other tabs that refresh at the same moment are
// covered by the server's short grace window.
function refreshOnce() {
  if (!refreshPromise) {
    refreshPromise = bareClient
      .post('/auth/refresh', null, { headers: { 'X-CSRF-Token': getCookie(CSRF_COOKIE) ?? '' } })
      .finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

apiClient.interceptors.request.use((config) => {
  if (!SAFE_METHODS.has((config.method ?? 'get').toLowerCase())) {
    const csrf = getCookie(CSRF_COOKIE)
    if (csrf) config.headers['X-CSRF-Token'] = csrf
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => {
    if (response.config?.url?.includes('/auth/login')) expiryEventSent = false
    return response
  },
  async (error) => {
    const status = error.response?.status
    const original = error.config ?? {}
    const url = original.url ?? ''
    const isAuthCall = AUTH_URLS.some((path) => url.includes(path))
    const hadSession = hasSessionCookie()

    if (status === 401 && hadSession && !isAuthCall) {
      // The 15-minute access cookie probably just lapsed: renew it quietly and
      // replay the request once. Only if that fails is the user really logged out.
      if (!original._retried) {
        original._retried = true
        try {
          await refreshOnce()
          return apiClient(original)
        } catch {
          /* fall through to the expiry handling below */
        }
      }
      forgetSessionCookie()
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
