import apiClient from './client'

export function fetchMyResumes(includeArchived = false) {
  const params = typeof includeArchived === 'object' ? includeArchived : (includeArchived ? { include_archived: true } : {})
  return apiClient.get('/resumes', { params }).then((res) => res.data)
}
export const fetchResumes = fetchMyResumes

export function fetchResumesPage(filters = {}) {
  const params = { ...filters }
  return apiClient.get('/resumes', { params }).then((res) => {
    const items = Array.isArray(res.data) ? res.data : (res.data.items ?? res.data.results ?? [])
    return { items, total: Number(res.headers['x-total-count'] ?? res.data.total ?? items.length) }
  })
}

export function uploadResumesBulk(files, onUploadProgress) {
  const form = new FormData(); files.forEach((file) => form.append('files', file))
  return apiClient.post('/resumes/bulk', form, { headers: { 'Content-Type': 'multipart/form-data' }, onUploadProgress }).then((res) => res.data)
}
export function fetchResume(resumeId) { return apiClient.get(`/resumes/${resumeId}`).then((res) => res.data) }
export function uploadResume(file) {
  const form = new FormData(); form.append('file', file)
  return apiClient.post('/resumes', form, { headers: { 'Content-Type': 'multipart/form-data' } }).then((res) => res.data)
}
export function archiveResume(resumeId, archived) { return apiClient.patch(`/resumes/${resumeId}/archive`, null, { params: { archived } }).then((res) => res.data) }
export function deleteResume(resumeId) { return apiClient.delete(`/resumes/${resumeId}`) }
export async function fetchResumeBlobUrl(resumeId) { const res = await apiClient.get(`/resumes/${resumeId}/file`, { responseType: 'blob' }); return window.URL.createObjectURL(res.data) }
export async function openResumeFile(resumeId) { const url = await fetchResumeBlobUrl(resumeId); window.open(url, '_blank', 'noopener,noreferrer'); setTimeout(() => window.URL.revokeObjectURL(url), 30000) }
export function fetchAllResumes() { return apiClient.get('/resumes', { params: { limit: 200 } }).then((res) => Array.isArray(res.data) ? res.data : (res.data.items ?? [])) }
// Backend route is POST /resumes/{id}/extract-skills (it resets status to PENDING and queues the task).
export function rerunResumeExtraction(resumeId) { return apiClient.post(`/resumes/${resumeId}/extract-skills`).then((res) => res.data) }
export const retryResumeExtraction = rerunResumeExtraction
