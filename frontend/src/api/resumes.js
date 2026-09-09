import apiClient from './client'

export function fetchMyResumes(includeArchived = false) {
  return apiClient
    .get('/resumes', { params: includeArchived ? { include_archived: true } : {} })
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

export async function openResumeFile(resumeId) {
  const res = await apiClient.get(`/resumes/${resumeId}/file`, { responseType: 'blob' })
  const url = window.URL.createObjectURL(res.data)
  window.open(url, '_blank', 'noopener,noreferrer')
  setTimeout(() => window.URL.revokeObjectURL(url), 30000)
}
