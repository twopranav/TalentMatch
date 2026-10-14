import apiClient from './client'
export function fetchOverview() { return apiClient.get('/v1/overview').then((res) => res.data) }
export function fetchAdminHealthMetrics() { return apiClient.get('/v1/admin/health-metrics').then((res) => res.data) }
