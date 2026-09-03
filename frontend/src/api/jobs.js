import apiClient from './client'

// status: optional "draft" | "published" | "closed" — ignored server-side
// for USER role, which is always restricted to published jobs regardless
export function fetchJobs(status) {
  return apiClient
    .get('/jobs', { params: status ? { status } : {} })
    .then((res) => res.data)
}

export function fetchJob(jobId) {
  return apiClient.get(`/jobs/${jobId}`).then((res) => res.data)
}