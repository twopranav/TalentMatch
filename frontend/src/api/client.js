import axios from 'axios'

// All backend calls should go through this instance, not raw axios/fetch,
// so auth headers and error handling stay in one place as the app grows.
const apiClient = axios.create({
  baseURL: '/api',
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const url = error.config?.url ?? ''
    const hadToken = !!localStorage.getItem('access_token')
    if (status === 401 && hadToken && !url.includes('/auth/login')) {
      localStorage.removeItem('access_token')
      if (window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient