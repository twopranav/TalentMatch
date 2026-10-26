import apiClient from './client'

export function fetchOverview() {
  return apiClient.get('/overview').then((response) => response.data)
}

export function fetchAdminHealthMetrics() {
  return apiClient.get('/admin/health-metrics').then((response) => response.data)
}
