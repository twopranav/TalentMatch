import apiClient from './client'

// Shared query parameters for job listing and pagination.
function buildJobParams(filters = {}) {
  const params = {}

  if (filters.status) params.status = filters.status
  if (filters.location) params.location = filters.location
  if (filters.employment_type) params.employment_type = filters.employment_type
  if (filters.seniority) params.seniority = filters.seniority
  if (filters.remote_type) params.remote_type = filters.remote_type
  if (filters.department) params.department = filters.department
  if (filters.q) params.q = filters.q
  if (filters.created_by) params.created_by = filters.created_by
  if (filters.limit != null) params.limit = filters.limit
  if (filters.offset != null) params.offset = filters.offset

  return params
}

// Fetch jobs using the existing response shape.
export function fetchJobs(filters = {}) {
  return apiClient
    .get('/jobs', { params: buildJobParams(filters) })
    .then((res) => res.data)
}

// Fetch a paginated job list.
// Returns { items: [...], total: number } for useJobs.js.
export function fetchJobsPage(filters = {}) {
  return apiClient
    .get('/jobs', { params: buildJobParams(filters) })
    .then((res) => {
      const payload = res.data
      const body = payload?.data ?? payload

      let items = []

      if (Array.isArray(body)) {
        items = body
      } else if (Array.isArray(body?.items)) {
        items = body.items
      } else if (Array.isArray(body?.jobs)) {
        items = body.jobs
      } else if (Array.isArray(payload?.items)) {
        items = payload.items
      } else if (Array.isArray(payload?.jobs)) {
        items = payload.jobs
      }

      const headerTotal = res.headers?.['x-total-count']

      const reportedTotal =
        headerTotal ??
        body?.total ??
        body?.total_count ??
        body?.count ??
        payload?.total ??
        payload?.total_count

      const parsedTotal = Number(reportedTotal)

      return {
        items,
        total:
          reportedTotal != null && Number.isFinite(parsedTotal)
            ? parsedTotal
            : items.length,
      }
    })
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

// Manually rerun JD skills extraction.
export function reextractJobSkills(jobId) {
  return apiClient
    .post(`/jobs/${jobId}/extract-skills`)
    .then((res) => res.data)
}

// Send the recruiter's complete corrected skill list.
export function updateJobSkills(jobId, skills) {
  return apiClient
    .put(`/jobs/${jobId}/skills`, { skills })
    .then((res) => res.data)
}
