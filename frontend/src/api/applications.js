import apiClient from './client'

export function applyToJob(jobId) {
  return apiClient.post('/applications', { job_id: jobId }).then((res) => res.data)
}

export function fetchMyApplications() {
  return apiClient.get('/applications/me').then((res) => res.data)
}

export function fetchJobApplications(jobId) {
  return apiClient.get(`/applications/job/${jobId}`).then((res) => res.data)
}

export function updateApplicationStatus(applicationId, statusValue) {
  return apiClient.patch(`/applications/${applicationId}/status`, { status: statusValue }).then((res) => res.data)
}

export function withdrawApplication(applicationId) {
  return apiClient.delete(`/applications/${applicationId}`)
}