import apiClient from './client'
export function applyToJob(jobId) { return apiClient.post('/applications', { job_id: jobId }).then((res) => res.data) }
export function fetchMyApplications(params = {}) { return apiClient.get('/applications/me', { params }).then((res) => res.data) }
export function fetchJobApplications(jobId) { return apiClient.get(`/applications/job/${jobId}`).then((res) => res.data) }
export function updateApplicationStatus(applicationId, statusValue) { return apiClient.patch(`/applications/${applicationId}/status`, { status: statusValue }).then((res) => res.data) }
export function updateShortlistStage(applicationId, stage, interviewAt = null) { return apiClient.patch(`/applications/${applicationId}/shortlist-stage`, { stage, interview_at: interviewAt }).then((res) => res.data) }
export function withdrawApplication(applicationId) { return apiClient.delete(`/applications/${applicationId}`) }
export function rescoreJobApplications(jobId) { return apiClient.post(`/applications/job/${jobId}/rescore`).then((res) => res.data) }
export function bulkApplyResumes(jobId, resumeIds) { return apiClient.post(`/applications/job/${jobId}/bulk`, { resume_ids: resumeIds }).then((res) => res.data) }
export function fetchJobApplicationsPage(jobId, filterParams, limit, offset) {
  const params = new URLSearchParams(filterParams); params.set('limit', limit); params.set('offset', offset)
  return apiClient.get(`/applications/job/${jobId}`, { params }).then((res) => ({ items: Array.isArray(res.data) ? res.data : (res.data.items ?? []), total: Number(res.headers['x-total-count'] ?? res.data.total ?? res.data.length) }))
}
export function fetchApplicationNotes(applicationId) { return apiClient.get(`/applications/${applicationId}/notes`).then((res) => res.data) }
export function addApplicationNote(applicationId, body) { return apiClient.post(`/applications/${applicationId}/notes`, { body }).then((res) => res.data) }
export function updateManualScore(applicationId, manualScore) { return apiClient.patch(`/applications/${applicationId}/manual-score`, { manual_score: manualScore }).then((res) => res.data) }
export function bulkUpdateApplicationStatus(jobId, applicationIds, status) {
  return apiClient.post(`/v1/jobs/${jobId}/applications/bulk-status`, { application_ids: applicationIds, status }).then((res) => res.data)
}
export function updateInterview(applicationId, stage, interviewAt = null) { return apiClient.patch(`/applications/${applicationId}/interview`, { stage, interview_at: interviewAt }).then((res) => res.data) }
export function fetchStageCounts() { return apiClient.get('/applications/stage-counts').then((res) => res.data) }
// Upload resume files and apply each to this job in one request (POST /applications/job/{id}/bulk-upload).
export function bulkUploadAndApply(jobId, files) {
  const form = new FormData(); files.forEach((file) => form.append('files', file))
  return apiClient.post(`/applications/job/${jobId}/bulk-upload`, form, { headers: { 'Content-Type': 'multipart/form-data' } }).then((res) => res.data)
}
