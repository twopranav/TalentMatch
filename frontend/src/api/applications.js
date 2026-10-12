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

// stage: 'shortlisted' | 'review' | 'interview_scheduled' | 'rejected'.
// interviewAt (ISO string with timezone) is required for 'interview_scheduled'.
export function updateShortlistStage(applicationId, stage, interviewAt = null) {
  return apiClient
    .patch(`/applications/${applicationId}/shortlist-stage`, { stage, interview_at: interviewAt })
    .then((res) => res.data)
}

export function withdrawApplication(applicationId) {
  return apiClient.delete(`/applications/${applicationId}`)
}

export function rescoreJobApplications(jobId) {
  return apiClient.post(`/applications/job/${jobId}/rescore`).then((res) => res.data)
}

export function bulkApplyResumes(jobId, resumeIds) {
  return apiClient
    .post(`/applications/job/${jobId}/bulk`, { resume_ids: resumeIds })
    .then((res) => res.data)
}
// One page of a job's applicants. Returns { items, total }: total is the size
// of the whole filtered list (the X-Total-Count header), not just this page.
export function fetchJobApplicationsPage(jobId, filterParams, limit, offset) {
  const params = new URLSearchParams(filterParams)
  params.set('limit', limit)
  params.set('offset', offset)
  return apiClient.get(`/applications/job/${jobId}`, { params }).then((res) => ({
    items: res.data,
    total: Number(res.headers['x-total-count'] ?? res.data.length),
  }))
}
