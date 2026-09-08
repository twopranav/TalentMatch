import apiClient from './client'

// filters: { status, location, employment_type, seniority, remote_type, department }
// Only truthy keys are sent, so "all"/empty stays server-default.
export function fetchJobs(filters = {}) {
  const params = {}
  if (filters.status) params.status = filters.status
  if (filters.location) params.location = filters.location
  if (filters.employment_type) params.employment_type = filters.employment_type
  if (filters.seniority) params.seniority = filters.seniority
  if (filters.remote_type) params.remote_type = filters.remote_type
  if (filters.department) params.department = filters.department

  return apiClient.get('/jobs', { params }).then((res) => res.data)
}

export function fetchJob(jobId) {
  return apiClient.get(`/jobs/${jobId}`).then((res) => res.data)
}

export function createJob(payload) {
  return apiClient.post('/jobs', payload).then((res) => res.data)
}

export function updateJob(jobId, payload) {
  return apiClient.patch(`/jobs/${jobId}`, payload).then((res) => res.data)
}

export function deleteJob(jobId) {
  return apiClient.delete(`/jobs/${jobId}`)
}

export function uploadJobDescription(jobId, file) {
  const form = new FormData()
  form.append('file', file)
  return apiClient
    .post(`/jobs/${jobId}/jd`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((res) => res.data)
}