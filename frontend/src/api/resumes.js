import apiClient from './client'

export function fetchMyResumes(includeArchived = false) {
  return apiClient
    .get('/resumes', { params: includeArchived ? { include_archived: true } : {} })
    .then((res) => res.data)
}

// Same endpoint as fetchMyResumes — the backend already returns every
// resume in the system to recruiter/admin/superuser (not just their own),
// this is just a clearer name for that use on the recruiter-facing library.
export const fetchResumes = fetchMyResumes

export function uploadResumesBulk(files) {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  return apiClient
    .post('/resumes/bulk', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((res) => res.data)
}

export function fetchResume(resumeId) {
  return apiClient.get(`/resumes/${resumeId}`).then((res) => res.data)
}

export function uploadResume(file) {
  const form = new FormData()
  form.append('file', file)
  return apiClient
    .post('/resumes', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((res) => res.data)
}

export function archiveResume(resumeId, archived) {
  return apiClient
    .patch(`/resumes/${resumeId}/archive`, null, { params: { archived } })
    .then((res) => res.data)
}

export function deleteResume(resumeId) {
  return apiClient.delete(`/resumes/${resumeId}`)
}

export async function fetchResumeBlobUrl(resumeId) {
  const res = await apiClient.get(`/resumes/${resumeId}/file`, { responseType: 'blob' })
  return window.URL.createObjectURL(res.data)
}

export async function openResumeFile(resumeId) {
  const url = await fetchResumeBlobUrl(resumeId)
  window.open(url, '_blank', 'noopener,noreferrer')
  setTimeout(() => window.URL.revokeObjectURL(url), 30000)
}