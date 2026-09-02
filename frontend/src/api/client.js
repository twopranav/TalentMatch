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

export default apiClient
