import apiClient from './client'

function jobParams(filters = {}) {
  const params = {}
  for (const key of ['status', 'location', 'employment_type', 'seniority', 'remote_type', 'department', 'q', 'limit', 'offset', 'created_by']) {
    if (filters[key] !== undefined && filters[key] !== null && filters[key] !== '') params[key] = filters[key]
  }
  return params
}

// Array return shape retained for existing callers.
export function fetchJobs(filters = {}) {
  return apiClient.get('/jobs', { params: jobParams(filters) }).then((res) => res.data)
}

// Paginated listing used by desktop tables. Supports JSON array responses and
// enveloped {items,total} responses without breaking the legacy fetchJobs API.
export function fetchJobsPage(filters = {}) {
  return apiClient.get('/jobs', { params: jobParams(filters) }).then((res) => {
    const items = Array.isArray(res.data) ? res.data : (res.data.items ?? res.data.results ?? [])
    return { items, total: Number(res.headers['x-total-count'] ?? res.data.total ?? items.length) }
  })
}

export function fetchJob(jobId) { return apiClient.get(`/jobs/${jobId}`).then((res) => res.data) }
export function createJob(payload) { return apiClient.post('/jobs', payload).then((res) => res.data) }
export function updateJob(jobId, payload) { return apiClient.patch(`/jobs/${jobId}`, payload).then((res) => res.data) }
export function deleteJob(jobId) { return apiClient.delete(`/jobs/${jobId}`) }
export function uploadJobDescription(jobId, file) {
  const form = new FormData(); form.append('file', file)
  return apiClient.post(`/jobs/${jobId}/jd`, form, { headers: { 'Content-Type': 'multipart/form-data' } }).then((res) => res.data)
}
export function reextractJobSkills(jobId) { return apiClient.post(`/jobs/${jobId}/extract-skills`).then((res) => res.data) }
export function updateJobSkills(jobId, skills) { return apiClient.put(`/jobs/${jobId}/skills`, { skills }).then((res) => res.data) }
